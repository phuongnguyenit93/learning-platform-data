# Tách interface theo nhu cầu sử dụng và tránh interface quá lớn

Interface Segregation Principle (ISP), thường dịch là **nguyên tắc phân tách interface**, là chữ I trong bộ nguyên tắc SOLID. Nguyên tắc này nói rằng một client không nên bị buộc phụ thuộc vào những phương thức mà nó không sử dụng. Khi một interface gom quá nhiều khả năng không liên quan đến mọi bên gọi, các lớp triển khai có thể phải cung cấp những phương thức vô nghĩa, còn client phải biết đến một hợp đồng rộng hơn nhu cầu thực tế.

Trong Java, có thể áp dụng ISP bằng cách thiết kế các interface nhỏ, có mục đích rõ ràng theo vai trò của client hoặc theo một khả năng nghiệp vụ thống nhất. Một lớp vẫn có thể triển khai nhiều interface nếu nó thực sự hỗ trợ nhiều khả năng. Mục tiêu không phải là tạo interface cho từng phương thức, mà là để mỗi client chỉ phụ thuộc vào hợp đồng cần thiết.

## 1. Vấn đề của một interface quá lớn

Hãy hình dung một ứng dụng văn phòng có máy in cơ bản, máy quét và máy đa chức năng. Nếu mọi thiết bị đều phải triển khai một interface duy nhất gồm `print`, `scan` và `fax`, máy in cơ bản phải khai báo cả những thao tác mà nó không hỗ trợ.

~~~java
interface OfficeMachine {
    void print(String document);
    String scan();
    void fax(String number, String document);
}

class BasicPrinter implements OfficeMachine {
    @Override
    public void print(String document) {
        System.out.println("Print: " + document);
    }

    @Override
    public String scan() {
        throw new UnsupportedOperationException("Scanning is unavailable");
    }

    @Override
    public void fax(String number, String document) {
        throw new UnsupportedOperationException("Fax is unavailable");
    }
}
~~~

Đây là ví dụ minh họa cho thiết kế có vấn đề. Mã vẫn có thể biên dịch, nhưng hợp đồng `OfficeMachine` tuyên bố rằng mọi implementation đều có thể quét và fax, trong khi `BasicPrinter` không thể thực hiện hai thao tác đó. Client chỉ cần in vẫn phải phụ thuộc vào một interface mô tả cả scan và fax. Khi interface tiếp tục lớn lên, mỗi implementation có thể phải viết thêm phương thức rỗng, ném ngoại lệ hoặc hành vi giả để thỏa mãn hợp đồng.

Những dấu hiệu thường gặp của interface quá lớn:

- Một số implementation chỉ hỗ trợ một phần phương thức, còn các phương thức khác phải để trống hoặc ném `UnsupportedOperationException`.
- Thay đổi một nhóm phương thức có thể khiến nhiều lớp không liên quan phải sửa hoặc biên dịch lại.
- Client nhận một kiểu tổng quát rồi phải kiểm tra kiểu thực tế bằng `instanceof` hoặc ép kiểu để tìm khả năng mà nó cần.
- Test double hoặc mock phải triển khai nhiều phương thức không liên quan đến hành vi đang kiểm thử.
- Tên interface quá chung, chẳng hạn `Manager`, `Service` hay `Worker`, nhưng lại chứa nhiều nhóm trách nhiệm không cùng một vai trò.

Một interface có nhiều phương thức chưa chắc đã vi phạm ISP. Vấn đề xuất hiện khi các client khác nhau phụ thuộc vào những phần hợp đồng khác nhau và phải gánh những phương thức không cần thiết.

## 2. Tách theo khả năng hoặc vai trò của client

Thay vì buộc mọi thiết bị dùng một hợp đồng chung, hãy định nghĩa những interface nhỏ hơn theo các khả năng thực sự có ý nghĩa:

~~~java
interface Printable {
    void print(String document);
}

interface Scannable {
    String scan();
}

interface Faxable {
    void fax(String number, String document);
}
~~~

Giờ đây, máy in cơ bản chỉ triển khai `Printable`. Máy đa chức năng có thể triển khai cả `Printable`, `Scannable` và `Faxable`. Client muốn in chỉ cần nhận một `Printable`, không cần biết thiết bị đó có quét hay fax hay không.

~~~java
class BasicPrinter implements Printable {
    @Override
    public void print(String document) {
        System.out.println("Print: " + document);
    }
}

class OfficeMfp implements Printable, Scannable, Faxable {
    @Override
    public void print(String document) {
        System.out.println("Print: " + document);
    }

    @Override
    public String scan() {
        return "scanned-page";
    }

    @Override
    public void fax(String number, String document) {
        System.out.println("Fax " + document + " to " + number);
    }
}
~~~

Các interface này mô tả hợp đồng mà client cần. Một lớp có thể kết hợp nhiều khả năng bằng cách triển khai nhiều interface; không cần tạo một interface lớn để đại diện cho mọi tổ hợp thiết bị có thể có.

### ISP thay đổi quan hệ phụ thuộc như thế nào?

Trước khi tách, phương thức chỉ in có thể yêu cầu `OfficeMachine`, khiến client phụ thuộc cả scan và fax:

~~~java
void printReport(OfficeMachine machine) {
    machine.print("report.pdf");
}
~~~

Sau khi tách, phương thức chỉ yêu cầu khả năng in:

~~~java
void printReport(Printable printer) {
    printer.print("report.pdf");
}
~~~

Cả `BasicPrinter` và `OfficeMfp` đều có thể truyền vào `printReport`. Client không cần nhánh điều kiện để hỏi thiết bị có hỗ trợ scan hay fax hay không. Hợp đồng tham số thể hiện đúng nhu cầu của phương thức.

## 3. Ví dụ Java 17+ hoàn chỉnh

Lưu đoạn mã sau vào tệp `InterfaceSegregationDemo.java`. Ví dụ dùng các interface lồng trong lớp demo để chỉ cần một tệp nguồn và chạy độc lập.

~~~java
public class InterfaceSegregationDemo {
    interface Printable {
        void print(String document);
    }

    interface Scannable {
        String scan();
    }

    interface Faxable {
        void fax(String number, String document);
    }

    static final class BasicPrinter implements Printable {
        @Override
        public void print(String document) {
            System.out.println("Print: " + document);
        }
    }

    static final class OfficeMfp implements Printable, Scannable, Faxable {
        @Override
        public void print(String document) {
            System.out.println("Print: " + document);
        }

        @Override
        public String scan() {
            return "scanned-page";
        }

        @Override
        public void fax(String number, String document) {
            System.out.println("Fax " + document + " to " + number);
        }
    }

    static void printReport(Printable printer) {
        printer.print("report.pdf");
    }

    static void scanDocument(Scannable scanner) {
        System.out.println("Scan: " + scanner.scan());
    }

    public static void main(String[] args) {
        Printable basicPrinter = new BasicPrinter();
        printReport(basicPrinter);

        OfficeMfp mfp = new OfficeMfp();
        printReport(mfp);
        scanDocument(mfp);
        mfp.fax("555-0100", "invoice.pdf");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac --release 17 InterfaceSegregationDemo.java
java InterfaceSegregationDemo
~~~

Kết quả stdout chính xác:

~~~text
Print: report.pdf
Print: report.pdf
Scan: scanned-page
Fax invoice.pdf to 555-0100
~~~

Ví dụ minh họa ba điểm:

1. `BasicPrinter` chỉ cần triển khai `Printable`; nó không khai báo các thao tác mà thiết bị không hỗ trợ.
2. `OfficeMfp` kết hợp ba khả năng bằng cách triển khai ba interface độc lập.
3. `printReport` và `scanDocument` nhận các kiểu khác nhau theo đúng nhu cầu của từng client. Phương thức in không phụ thuộc vào hợp đồng quét hoặc fax.

Các kiểu lồng bên trong `InterfaceSegregationDemo` là những interface và lớp thành viên được khai báo theo cú pháp Java. Chúng được truy cập trong ví dụ qua tên đơn giản vì nằm trong cùng lớp bao. Đây là chương trình chạy đầy đủ; các đoạn ở phần trước là những mảnh mã dùng để giải thích thiết kế.

## 4. ISP liên hệ với tính kết dính và sự thay đổi

Tách interface giúp giảm phạm vi phụ thuộc. Khi client chỉ nhận `Printable`, thay đổi riêng hợp đồng `Scannable` thường không cần thay đổi chữ ký hay logic của client in. Điều này làm cho các phần ít liên quan có thể tiến hóa độc lập hơn.

ISP cũng giúp hợp đồng thể hiện tính kết dính (cohesion): các phương thức nằm cùng một interface nên phục vụ một vai trò hoặc một nhóm client có nhu cầu gần nhau. Nếu hai nhóm client thay đổi vì những lý do khác nhau và chỉ sử dụng các nhóm phương thức riêng biệt, đó là tín hiệu để xem xét tách interface.

| Khía cạnh | Interface quá lớn | Interface được phân tách |
| --- | --- | --- |
| Hợp đồng client | Phụ thuộc nhiều khả năng cùng lúc | Phụ thuộc khả năng đang cần |
| Implementation | Có thể phải cung cấp phương thức không hỗ trợ | Chỉ triển khai khả năng thật sự có |
| Thay đổi API | Dễ ảnh hưởng đến lớp không liên quan | Thường giới hạn ở nhóm client liên quan |
| Kiểm thử | Mock có thể cần nhiều phương thức dư thừa | Mock nhỏ và sát hành vi cần kiểm tra |
| Kết hợp chức năng | Một interface đại diện mọi tổ hợp | Lớp kết hợp nhiều interface khi cần |

ISP không đảm bảo mọi thay đổi chỉ ảnh hưởng một lớp. Nếu client thực sự cần nhiều khả năng hoặc nhiều interface cùng thay đổi vì một khái niệm nghiệp vụ chung, chúng vẫn có thể phụ thuộc lẫn nhau. Nguyên tắc này giúp chọn đúng ranh giới phụ thuộc thay vì cố gắng loại bỏ mọi quan hệ.

## 5. Phân biệt ISP với các nguyên tắc gần nhau

**Single Responsibility Principle (SRP)** tập trung vào lý do để một module hoặc lớp thay đổi. **Interface Segregation Principle (ISP)** tập trung vào hợp đồng mà client phụ thuộc vào. Hai nguyên tắc liên quan nhưng không đồng nghĩa: một lớp có thể có trách nhiệm rõ ràng nhưng vẫn triển khai một interface quá rộng; ngược lại, một interface nhỏ không tự bảo đảm implementation chỉ có một trách nhiệm.

**Dependency Inversion Principle (DIP)** nói về việc các module cấp cao và cấp thấp phụ thuộc vào abstraction phù hợp. ISP giúp làm các abstraction đó nhỏ và sát nhu cầu client. Một interface nhỏ vẫn có thể được dùng sai nếu client cấp cao phụ thuộc vào abstraction không phù hợp.

**Open/Closed Principle (OCP)** khuyến khích mở rộng hành vi mà không phải liên tục sửa mã đã ổn định. Các interface theo khả năng có thể giúp bổ sung implementation mới dễ hơn, nhưng việc tách interface tự nó không bảo đảm OCP.

Có thể ghi nhớ: ISP hỏi “client có phải phụ thuộc vào những phương thức nó không cần không?”, còn SRP hỏi “module này có những lý do thay đổi không liên quan nào?”.

## 6. Không nên tách interface một cách máy móc

ISP không yêu cầu tạo một interface riêng cho mọi phương thức. Việc tách quá mức làm tăng số kiểu cần hiểu, tên gọi, quan hệ giữa các abstraction và chi phí bảo trì. Các phương thức nên nằm cùng nhau nếu chúng biểu đạt một hợp đồng có ý nghĩa và thường được client sử dụng cùng nhau.

Ví dụ, một hợp đồng `InputStream` không trở nên tốt hơn chỉ vì ta tách `read()` và `close()` thành các interface rời rạc trong mọi trường hợp. Hai thao tác có thể thuộc cùng một abstraction vì vòng đời và cách sử dụng của luồng gắn bó với nhau. Quyết định cần dựa vào nhu cầu client và ngữ nghĩa của hợp đồng, không chỉ dựa vào số lượng phương thức.

Tránh những kiểu tách sau:

- **Một interface cho mỗi getter hoặc setter** khi chúng chỉ tạo ra nhiều kiểu vụn vặt mà không biểu đạt vai trò độc lập.
- **Interface rỗng hoặc tên quá mơ hồ** chỉ để ép lớp vào một cấu trúc phân cấp.
- **Tách nhưng vẫn yêu cầu client phụ thuộc tất cả interface** thông qua một tham số hoặc abstraction tổng hợp không cần thiết.
- **Dùng `instanceof` hoặc ép kiểu khắp nơi** để tìm các khả năng bị che giấu. Nếu client cần một khả năng, nên yêu cầu trực tiếp interface thể hiện khả năng đó.
- **Giữ phương thức giả** trả về `null`, làm việc không có tác dụng hoặc ném ngoại lệ chỉ để lớp thỏa mãn interface.
- **Tách các thao tác có quan hệ nghiệp vụ chặt chẽ** khiến client phải tự điều phối một quy trình mà lẽ ra phải là một hợp đồng nhất quán.

Một interface tổng hợp vẫn hữu ích nếu một client cụ thể thực sự cần toàn bộ các khả năng. Có thể định nghĩa `interface MultifunctionDevice extends Printable, Scannable, Faxable {}` để đặt tên cho tổ hợp đó. Các client chỉ in vẫn nên nhận `Printable`; chúng không cần phụ thuộc `MultifunctionDevice`.

## 7. Thiết kế interface theo nhu cầu client

Một quy trình thực tế để áp dụng ISP:

1. **Liệt kê các client.** Xác định các lớp, dịch vụ hoặc use case gọi đến hợp đồng hiện tại.
2. **Đánh dấu phương thức được dùng.** Lập bảng client–phương thức để thấy các nhóm nhu cầu thực tế; không giả định mọi client cần mọi phương thức.
3. **Tìm nhóm hợp đồng có ý nghĩa.** Gom các phương thức theo vai trò, khả năng hoặc nhóm client liên quan.
4. **Tạo interface chuyên biệt.** Chọn tên diễn đạt hành vi mà client yêu cầu, ví dụ `Printable`, `Scannable`, `Clock` hoặc `MessageSender`.
5. **Điều chỉnh implementation.** Cho mỗi lớp triển khai các interface tương ứng với khả năng thực tế. Nếu một lớp hỗ trợ nhiều vai trò, triển khai nhiều interface.
6. **Thu hẹp kiểu tham số và trường.** Để client phụ thuộc interface nhỏ nhất đáp ứng được công việc của nó.
7. **Kiểm thử các hành vi quan trọng.** Kiểm tra client chỉ gọi đúng khả năng cần dùng và các implementation thực hiện đúng hợp đồng.
8. **Xem lại API công khai.** Nếu interface hiện tại đã được bên khác sử dụng, lên kế hoạch chuyển đổi tương thích thay vì xóa hoặc đổi hợp đồng một cách đột ngột.

Ví dụ bảng nhu cầu ban đầu có thể trông như sau:

| Client | In | Quét | Fax |
| --- | --- | --- | --- |
| `ReportPrinter` | Có | Không | Không |
| `ArchiveService` | Không | Có | Không |
| `LegacyFaxSender` | Không | Không | Có |
| `OfficeConsole` | Có | Có | Có |

Ba client đầu chỉ cần các interface tương ứng với một khả năng. `OfficeConsole` có thể nhận nhiều interface hoặc nhận một abstraction tổng hợp nếu thiết kế thực sự cần cả ba. Bảng này là công cụ phân tích nhu cầu, không phải quy tắc rằng mỗi cột bắt buộc phải trở thành interface mới.

## 8. ISP trong kiểm thử và mở rộng

Interface nhỏ thường làm cho test double dễ viết hơn. Nếu một dịch vụ chỉ cần in báo cáo, test có thể cung cấp một implementation giả của `Printable` mà không cần tạo các hành vi scan và fax. Test vì vậy tập trung vào hợp đồng thực sự liên quan.

Tương tự, khi thêm một loại thiết bị mới, lớp mới có thể triển khai đúng các khả năng mà nó hỗ trợ. Một máy in mạng chỉ cần `Printable`; một bộ chuyển tài liệu có thể cần `Scannable`; máy đa chức năng triển khai nhiều interface. Không cần sửa mọi implementation hiện có chỉ vì hệ thống bổ sung một khả năng độc lập.

Tuy vậy, ISP không thay thế kiểm thử hợp đồng. Một lớp khai báo `implements Printable` vẫn có thể in sai hoặc không tuân theo ý nghĩa của phương thức. Interface xác định hình dạng của hợp đồng ở mức kiểu; kiểm thử và tài liệu xác định hành vi mong đợi.

## 9. Lưu ý khi thay đổi một API đã tồn tại

Nếu một thư viện công khai đã có `OfficeMachine`, xóa interface hoặc thay đổi chữ ký phương thức có thể phá vỡ mã của người dùng thư viện. Trong trường hợp đó, hãy xem xét:

- Bổ sung các interface nhỏ như `Printable` và `Scannable`, rồi để implementation hiện có triển khai chúng.
- Cung cấp adapter giúp client chuyển từ hợp đồng cũ sang hợp đồng mới.
- Giữ interface cũ trong một giai đoạn chuyển tiếp nếu yêu cầu tương thích nhị phân hoặc nguồn.
- Đánh dấu API cũ là deprecated khi có chiến lược loại bỏ rõ ràng, đồng thời hướng dẫn người dùng chuyển sang hợp đồng mới.
- Không âm thầm thay đổi ý nghĩa phương thức cũ hoặc trả về kết quả giả chỉ để phù hợp với thiết kế mới.

Việc giữ interface cũ và cách nối nó với các interface mới phụ thuộc vào API thực tế. Không có một cách chuyển đổi tương thích duy nhất cho mọi thư viện; hãy kiểm tra các client đang tồn tại và mức tương thích mà dự án cam kết.

## 10. Những lỗi thiết kế thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Nhiều implementation ném `UnsupportedOperationException` | Interface đòi hỏi khả năng mà một số lớp không có | Tách hợp đồng theo khả năng; để lớp chỉ triển khai khả năng được hỗ trợ |
| Client ép kiểu sang lớp cụ thể | Kiểu tham số không diễn đạt khả năng mà client thực sự cần | Đưa khả năng vào interface riêng và nhận interface đó ở tham số |
| Thêm phương thức vào interface khiến nhiều lớp không liên quan phải sửa | Các client hoặc implementation phụ thuộc một hợp đồng quá rộng | Kiểm tra nhóm phương thức và phân tách theo nhu cầu ổn định |
| Có quá nhiều interface một phương thức | Tách theo cú pháp mà không dựa trên vai trò | Gộp những phương thức có ngữ nghĩa và nhu cầu sử dụng gắn bó |
| Interface tổng hợp xuất hiện ở khắp mọi nơi | Mọi client đều phụ thuộc vào tổ hợp lớn dù chỉ dùng một phần | Chỉ dùng kiểu tổng hợp cho client cần tất cả khả năng |
| Sửa API gây lỗi cho người dùng thư viện | Thay đổi hợp đồng công khai không có lộ trình tương thích | Bổ sung interface, adapter hoặc kế hoạch deprecation phù hợp |

Một `default` method trong Java có thể giúp một interface mở rộng về mặt tương thích trong một số trường hợp, nhưng không tự giải quyết vấn đề thiết kế. Nếu client vẫn phụ thuộc vào một hợp đồng lớn với nhiều khả năng không liên quan, cần xem xét lại ranh giới interface. Tương tự, chuyển phương thức thành `default` rồi để implementation không làm gì có thể che dấu vấn đề thay vì sửa nó.

## 11. Checklist trước khi chấp nhận một interface

- Tên interface có mô tả một vai trò hoặc một khả năng cụ thể không?
- Client sử dụng interface có phải biết đến phương thức mà nó không cần không?
- Các implementation có thể thực hiện đầy đủ ý nghĩa của hợp đồng mà chúng khai báo không?
- Có phương thức nào thường xuyên để trống, trả kết quả giả hoặc ném ngoại lệ vì không được hỗ trợ không?
- Các client khác nhau có dùng những nhóm phương thức tách biệt không?
- Có cần một interface tổng hợp cho một số client, trong khi các client khác chỉ cần interface nhỏ không?
- Việc tách có làm tăng số abstraction một cách khó hiểu mà không giảm phụ thuộc thực tế không?
- Nếu interface công khai đang được sử dụng, kế hoạch chuyển đổi có bảo vệ mức tương thích cần thiết không?
- Test có thể cung cấp implementation đơn giản của hợp đồng cần dùng mà không giả lập nhiều khả năng dư thừa không?

ISP là nguyên tắc thiết kế ranh giới phụ thuộc. Hãy để client khai báo nhu cầu bằng kiểu interface nhỏ và có ý nghĩa; để lớp triển khai kết hợp những khả năng mà nó thật sự hỗ trợ. Cách làm này giúp hợp đồng dễ hiểu, implementation trung thực với năng lực của nó và các thay đổi ít lan sang những phần không liên quan.
