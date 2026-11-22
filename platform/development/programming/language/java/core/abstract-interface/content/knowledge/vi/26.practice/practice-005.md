# Tách interface lớn thành các vai trò nhỏ

Tách một interface lớn thành các interface nhỏ theo vai trò là cách áp dụng **Interface Segregation Principle (ISP)** — nguyên lý phân tách interface trong SOLID. Nguyên lý này khuyên rằng một client không nên bị buộc phụ thuộc vào những thao tác mà nó không sử dụng. Thay vì một interface bao trùm mọi khả năng của hệ thống, hãy tạo các hợp đồng nhỏ, có ý nghĩa rõ ràng và gắn với từng nhóm nhu cầu.

Ví dụ, một thiết bị đa chức năng có thể in, quét và gửi fax. Nhưng một máy in cơ bản chỉ có khả năng in. Nếu cả hai buộc phải triển khai cùng một interface `Machine` với đủ ba phương thức, lớp máy in cơ bản phải cung cấp những phương thức không hỗ trợ hoặc ném ngoại lệ giả tạo. Chia hợp đồng thành `Printable`, `Scannable` và `Faxable` giúp mỗi lớp chỉ cam kết những khả năng nó thực sự có.

## 1. Nguyên lý ISP nói gì?

Robert C. Martin mô tả ISP theo hướng client nên phụ thuộc vào các interface nhỏ phù hợp với nhu cầu của mình. Một interface lớn có thể gom nhiều phương thức vì chúng cùng thuộc một đối tượng trong thế giới thực, nhưng điều đó chưa chắc có nghĩa chúng thuộc cùng một hợp đồng phần mềm.

ISP không yêu cầu mọi interface chỉ có một phương thức. Mục tiêu là gom các phương thức có liên quan và thường được sử dụng cùng nhau bởi cùng một nhóm client. Một interface có nhiều phương thức vẫn hợp lý nếu chúng tạo thành một vai trò nhất quán.

Có thể diễn đạt nguyên tắc bằng ba câu hỏi:

- Client này thực sự cần gọi những thao tác nào?
- Khi thêm một khả năng mới vào interface, những client nào bị buộc phải thay đổi dù không sử dụng khả năng đó?
- Mỗi implementation có thể thực hiện đúng tất cả phương thức mà nó cam kết không?

Nếu một nhóm client chỉ dùng một phần nhỏ của interface và những phần còn lại thay đổi độc lập, interface có thể đang đảm nhiệm quá nhiều vai trò.

## 2. Dấu hiệu của một interface quá lớn

Hãy hình dung hợp đồng `Machine` có các phương thức `print()`, `scan()` và `fax()`. Những dấu hiệu sau cho thấy nên xem xét phân tách:

- Một lớp chỉ hỗ trợ một phần phương thức và phải ném `UnsupportedOperationException` hoặc trả về giá trị giả cho các phương thức còn lại.
- Client chỉ dùng một số phương thức nhưng vẫn phụ thuộc vào toàn bộ interface. Việc thêm phương thức mới có thể buộc client hoặc implementation không liên quan phải sửa mã.
- Những nhóm phương thức thay đổi vì các lý do khác nhau. Chẳng hạn, khả năng quét tài liệu thay đổi theo loại scanner, trong khi khả năng gửi fax phụ thuộc vào cấu hình liên lạc.
- Các implementation cần những phụ thuộc khác nhau để đáp ứng các phương thức. Một máy in đơn giản không nên phải cấu hình dịch vụ fax.
- Kiểm thử trở nên khó hiểu vì một implementation giả phải khai báo nhiều hành vi không liên quan đến kịch bản đang kiểm tra.

Một interface nhiều phương thức tự nó chưa phải là vấn đề. Nếu mọi implementation cần toàn bộ phương thức và các phương thức cùng thuộc một hợp đồng gắn kết, tách interface có thể chỉ tạo thêm sự phức tạp.

## 3. Từ một interface lớn đến các interface theo vai trò

Trước khi phân tách, thiết kế thường có dạng:

```text
Machine
  ├── print(document)
  ├── scan()
  └── fax(document, destination)

BasicPrinter implements Machine
  └── chỉ có khả năng in

OfficeMultifunctionDevice implements Machine
  ├── in
  ├── quét
  └── fax
```

Với thiết kế này, `BasicPrinter` phải khai báo hành vi quét và fax dù phần cứng không hỗ trợ. Nếu triển khai bằng ngoại lệ, mọi client gọi nhầm phương thức chỉ phát hiện vấn đề lúc chạy. Nếu dùng phương thức rỗng, lỗi có thể bị che giấu.

Sau khi tách theo vai trò:

```text
Printable     Scannable     Faxable
     ^             ^            ^
     |             |            |
BasicPrinter   Scanner      FaxDevice

OfficeMultifunctionDevice implements
Printable, Scannable, Faxable
```

Một lớp có thể triển khai nhiều interface nhỏ nếu nó thật sự cung cấp nhiều khả năng. Một client chỉ cần in có thể phụ thuộc vào `Printable`; nó không cần biết đối tượng có thể quét hoặc gửi fax hay không.

## 4. Ví dụ Java hoàn chỉnh

Chương trình sau minh họa ba interface theo vai trò, một máy in chỉ in, một thiết bị đa chức năng và các dịch vụ phụ thuộc vào hợp đồng tối thiểu cần thiết.

Lưu toàn bộ mã vào `Main.java`:

```java
interface Printable {
    void print(String document);
}

interface Scannable {
    String scan();
}

interface Faxable {
    void fax(String document, String destination);
}

final class BasicPrinter implements Printable {
    @Override
    public void print(String document) {
        System.out.println("print:" + document);
    }
}

final class OfficeMultifunctionDevice
        implements Printable, Scannable, Faxable {
    @Override
    public void print(String document) {
        System.out.println("print:" + document);
    }

    @Override
    public String scan() {
        return "scanned-page";
    }

    @Override
    public void fax(String document, String destination) {
        System.out.println("fax:" + document + "->" + destination);
    }
}

final class PrintService {
    private final Printable printer;

    PrintService(Printable printer) {
        this.printer = printer;
    }

    void printInvoice(String invoice) {
        printer.print(invoice);
    }
}

final class ScanService {
    private final Scannable scanner;

    ScanService(Scannable scanner) {
        this.scanner = scanner;
    }

    void archive() {
        System.out.println("scan:" + scanner.scan());
    }
}

public class Main {
    public static void main(String[] args) {
        Printable basic = new BasicPrinter();
        PrintService printService = new PrintService(basic);
        printService.printInvoice("invoice-42");

        OfficeMultifunctionDevice office =
                new OfficeMultifunctionDevice();
        new ScanService(office).archive();
        office.fax("contract-7", "555-0100");
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```text
javac Main.java
java Main
```

Kết quả stdout chính xác:

```text
print:invoice-42
scan:scanned-page
fax:contract-7->555-0100
```

### Vì sao thiết kế này đáp ứng ISP?

- `BasicPrinter` chỉ triển khai `Printable`. Nó không cần khai báo phương thức quét hoặc fax.
- `OfficeMultifunctionDevice` triển khai cả ba interface vì nó thật sự cung cấp đủ ba khả năng.
- `PrintService` nhận một đối tượng kiểu `Printable`. Dịch vụ này không cần phụ thuộc vào scanner hay fax.
- `ScanService` chỉ yêu cầu `Scannable`. Có thể truyền một scanner độc lập hoặc thiết bị đa chức năng vào dịch vụ mà không đổi mã của dịch vụ.
- Các service nhận dependency qua constructor. Đây là constructor injection đơn giản: dependency được thể hiện ngay trong hợp đồng mà client cần.

Điểm quan trọng là kiểu tham số thể hiện đúng nhu cầu của client. Nếu `PrintService` nhận `OfficeMultifunctionDevice` trực tiếp, service sẽ phụ thuộc vào một implementation cụ thể và mất đi lợi ích của interface nhỏ.

## 5. Quy trình phân tách một interface trong dự án thực tế

Không nên tách interface chỉ bằng cách đếm số phương thức. Hãy đi từ các client và hành vi thực tế:

1. **Liệt kê client.** Xác định lớp hoặc module nào sử dụng interface, và ghi lại các phương thức mỗi client thực sự gọi.
2. **Nhóm phương thức theo vai trò.** Tìm các phương thức cùng phục vụ một nhu cầu, cùng thay đổi vì một lý do hoặc thường được sử dụng cùng nhau.
3. **Xác định hợp đồng nhỏ.** Tạo interface cho mỗi vai trò có ý nghĩa, với tên thể hiện khả năng hoặc trách nhiệm như `Readable`, `Writable`, `Searchable` hay `Exportable`.
4. **Cập nhật kiểu phụ thuộc của client.** Cho mỗi client nhận đúng interface nhỏ nhất đủ để thực hiện công việc. Ưu tiên phụ thuộc qua constructor hoặc phương thức thay vì tự tạo implementation bên trong client.
5. **Cập nhật implementation.** Một lớp chỉ triển khai những vai trò nó thực sự hỗ trợ. Lớp cần nhiều vai trò có thể implements nhiều interface.
6. **Loại bỏ hành vi giả.** Khi các interface nhỏ đã được áp dụng, xem lại những phương thức rỗng hoặc ngoại lệ chỉ tồn tại vì interface cũ quá rộng.
7. **Kiểm thử theo vai trò và hợp đồng.** Kiểm tra client hoạt động với mọi implementation hợp lệ của interface mà nó yêu cầu, kể cả implementation giả trong unit test.
8. **Đánh giá độ phức tạp sau khi tách.** Nếu một interface mới chỉ được dùng ở một nơi và không diễn tả một ranh giới có ý nghĩa, cân nhắc gộp lại.

Khi refactor hệ thống đang chạy, có thể giữ interface cũ làm lớp tương thích tạm thời và cho implementation hiện có triển khai các interface nhỏ mới. Sau khi client được chuyển sang hợp đồng mới, loại bỏ interface cũ trong một thay đổi có kiểm soát nếu không còn người dùng nào phụ thuộc vào nó. Việc giữ tương thích phụ thuộc vào yêu cầu API công khai và quy tắc phiên bản của dự án.

## 6. Những nguyên tắc thiết kế cần nhớ

**Interface nhỏ theo client, không nhất thiết nhỏ theo đối tượng.** Một thiết bị vật lý có thể làm nhiều việc, nhưng client đặt hàng in chỉ cần khả năng in. Hãy thiết kế hợp đồng quanh nhu cầu của client, đồng thời bảo đảm tên và hành vi của interface vẫn có ý nghĩa trong miền bài toán.

**Tách theo khả năng và trách nhiệm, không phải tách máy móc từng phương thức.** Tạo một interface cho mỗi phương thức đôi khi hữu ích, nhưng cũng có thể làm hệ thống khó hiểu nếu những thao tác luôn đi cùng nhau. ISP yêu cầu hợp đồng vừa đủ, không phải số lượng interface tối đa.

**Interface không phải nơi để khai báo mọi khả năng có thể tưởng tượng.** Chỉ thêm phương thức khi nó thuộc trách nhiệm của hợp đồng. Nếu một khả năng tùy chọn có thể được mô hình hóa thành một vai trò riêng, client không cần khả năng đó sẽ không phải phụ thuộc vào nó.

**Implementation có thể kết hợp nhiều vai trò.** Java cho phép một lớp implements nhiều interface. Việc tách interface không buộc phải tách một đối tượng thành nhiều lớp nếu những khả năng thực sự thuộc cùng một đối tượng và cùng vòng đời.

**ISP bổ trợ cho Dependency Inversion Principle (DIP).** DIP hướng tới phụ thuộc vào abstraction thay vì implementation cụ thể; ISP giúp abstraction đó không quá rộng đối với client. Hai nguyên lý bổ sung nhau: một client phụ thuộc vào một interface trừu tượng nhưng chứa quá nhiều phương thức vẫn có thể bị ảnh hưởng bởi thay đổi không liên quan.

## 7. Khi nào nên giữ interface lớn?

Giữ nguyên interface có thể là lựa chọn tốt nếu:

- Các phương thức tạo thành một hợp đồng gắn kết và hầu hết implementation hợp lệ đều cần chúng.
- Các client thường sử dụng gần như toàn bộ phương thức cùng nhau.
- Tách interface làm tăng số kiểu, tên và lớp chuyển tiếp mà không giảm sự phụ thuộc thực tế.
- Interface là API công khai đã ổn định và chi phí phá vỡ tương thích lớn hơn lợi ích của việc tách ngay. Có thể lên kế hoạch cho API nhỏ hơn ở phiên bản tiếp theo hoặc thêm các abstraction mới mà vẫn giữ đường tương thích.

Đừng nhầm việc một lớp có nhiều phương thức với vi phạm ISP. Cần xem mối liên hệ giữa client, hợp đồng và thay đổi trong hệ thống.

## 8. Các lỗi thường gặp

- **Tách theo số lượng thay vì trách nhiệm:** interface có một phương thức chưa chắc tốt hơn interface có ba phương thức liên quan.
- **Tạo interface chỉ để tránh một dependency trên giấy:** nếu client vẫn gọi nhiều abstraction rộng khác, vấn đề phụ thuộc có thể chưa được giải quyết.
- **Giữ client phụ thuộc vào implementation cụ thể:** phân tách interface mà các service vẫn khai báo tham số bằng lớp đa chức năng sẽ làm giảm lợi ích.
- **Để phương thức không được hỗ trợ trả về `null` hoặc không làm gì:** cách này che giấu vi phạm hợp đồng và tạo lỗi khó tìm. Nên xác định đúng khả năng mà implementation cam kết.
- **Chia quá vụn:** quá nhiều interface với ranh giới mơ hồ làm người đọc khó biết phải dùng kiểu nào. Đặt tên theo vai trò và giữ các phương thức liên quan cùng nhau.
- **Thay đổi API công khai mà không kiểm tra tương thích:** client bên ngoài có thể đang biên dịch dựa trên interface cũ. Hãy cân nhắc chiến lược chuyển đổi và kiểm thử tương thích.

## 9. Checklist rà soát

Trước khi hoàn tất việc phân tách, hãy kiểm tra:

- [ ] Mỗi interface có tên mô tả rõ một vai trò hoặc nhóm hành vi liên quan.
- [ ] Mỗi client chỉ phụ thuộc vào những thao tác nó cần.
- [ ] Mỗi implementation có thể đáp ứng đầy đủ hợp đồng mà nó implements.
- [ ] Không còn phương thức giả, rỗng hoặc ném ngoại lệ chỉ vì interface quá rộng.
- [ ] Client có thể được kiểm thử với implementation nhỏ hoặc test double phù hợp.
- [ ] Các lớp cần nhiều khả năng vẫn có thể implements nhiều interface.
- [ ] Việc thay đổi tương thích với các client và API hiện hữu đã được xem xét.

Tách interface lớn thành các vai trò nhỏ giúp giới hạn ảnh hưởng của thay đổi, làm rõ trách nhiệm và giúp implementation dễ thay thế hơn. Bắt đầu từ những client đang bị buộc phụ thuộc vào phương thức chúng không sử dụng; sau đó tạo các hợp đồng vừa đủ, chuyển client sang các hợp đồng đó và xác minh hành vi bằng kiểm thử.
