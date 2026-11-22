# Giới hạn hiệu năng và giới hạn dùng Scanner làm bộ phân tích định dạng phức tạp

## 1. Đặt Scanner vào đúng vai trò

`Scanner` giúp đọc văn bản theo token và chuyển token thành kiểu dữ liệu như `int`, `double` hoặc `BigDecimal`. Nó phù hợp khi cần mã dễ đọc, đầu vào tương đối đơn giản và tốc độ phân tích chưa phải nút thắt đã được đo.

Ví dụ, đọc vài trường từ chương trình dòng lệnh hoặc phân tích một dãy số ngắn bằng Scanner thường rõ ràng hơn tự viết toàn bộ logic tách và chuyển đổi.

Hai câu hỏi phải được tách riêng:

- **Đủ nhanh không?** Liên quan đến lượng dữ liệu, công việc phân tích, cấp phát bộ nhớ và thời gian chờ nguồn.
- **Đọc đúng định dạng không?** Liên quan đến dấu ngoặc kép, escape, cấu trúc lồng nhau, trường rỗng, kiểu dữ liệu và quy tắc bản ghi.

Đổi công cụ vì hiệu năng không tự làm định dạng được phân tích đúng. Ngược lại, một đoạn Scanner cho đúng kết quả với ba dòng mẫu chưa chứng minh nó xử lý đúng mọi đầu vào hợp lệ.

Bài dùng Java 17 trở lên và các cách tiếp cận còn được áp dụng hiện nay; không coi Scanner là API lỗi thời chỉ vì có những lựa chọn khác cho nhiệm vụ chuyên biệt.

## 2. Scanner phải làm nhiều việc hơn đọc ký tự

Một lượt đọc số có thể liên quan đến nhiều tầng:

~~~text
Byte đầu vào
  -> giải mã thành ký tự
  -> đọc/giữ dữ liệu trong bộ đệm
  -> nhận diện dấu phân cách và token
  -> kiểm tra dạng số theo locale/cơ số
  -> chuyển thành kiểu kết quả
  -> trả giá trị cho chương trình
~~~

Khi nguồn đã là `String` hoặc `Readable` cung cấp ký tự, bước giải mã byte thuộc về nơi khác hoặc không cần thực hiện. Dù vậy, công việc tách và phân tích token vẫn tồn tại.

Sự tiện lợi của Scanner đến từ các trách nhiệm nó đảm nhận:

- Dấu phân cách có thể là biểu thức chính quy.
- Có các phương thức đọc nhiều kiểu số.
- Có cấu hình locale và cơ số.
- Có kiểm tra token phù hợp kiểu hay không.
- Có bộ đệm và khả năng đọc thêm khi token chưa hoàn chỉnh.

Đây là những tính năng hữu ích, nhưng chúng có chi phí. Một bài toán chỉ cần đọc một số nguyên thập phân trên mỗi dòng có thể không cần toàn bộ mức linh hoạt ấy.

Không giải thích hiệu năng bằng câu “Scanner không có bộ đệm”. Scanner có bộ đệm nội bộ. Cần phân biệt chi phí đọc từ nguồn với chi phí nhận diện và chuyển đổi dữ liệu.

## 3. Những yếu tố thường làm chi phí tăng

| Yếu tố | Ảnh hưởng cần xem xét |
| --- | --- |
| Rất nhiều token nhỏ | Chi phí phân tích được lặp lại nhiều lần |
| Dấu phân cách hoặc mẫu tìm kiếm phức tạp | Công việc so khớp có thể tăng, tùy mẫu và dữ liệu |
| Locale/cách biểu diễn số linh hoạt | Kiểm tra và chuyển đổi không chỉ là ghép các chữ số |
| Tạo scanner mới liên tục | Thêm khởi tạo và cấp phát không cần thiết trong luồng token liên tục |
| Tạo nhiều chuỗi trung gian | Có thể tăng lượng cấp phát và công việc thu gom rác |
| Token hoặc dòng cực dài | Có thể làm tăng dữ liệu phải đệm/giữ |
| Dữ liệu sai xuất hiện thường xuyên | Thêm chi phí phát hiện, báo lỗi và phục hồi |
| In log cho từng token | Chi phí xuất dữ liệu có thể che lấp chi phí phân tích |

Các yếu tố này là điều cần kiểm tra, không phải công thức dự đoán tốc độ tuyệt đối. Không khẳng định Scanner luôn chậm hơn một lựa chọn khác bao nhiêu lần nếu chưa có phép đo phù hợp.

Việc gọi `hasNextInt()` rồi `nextInt()` cũng không nên bị mô tả đơn giản là “chắc chắn phân tích đầy đủ hai lần”: cách triển khai có thể lưu kết quả kiểm tra. Chỉ loại bỏ kiểm tra dữ liệu khi vẫn giữ được hành vi đúng, không tối ưu dựa trên suy đoán về nội bộ.

### Bọc thêm BufferedReader không loại bỏ mọi chi phí

`new Scanner(bufferedReader)` vẫn dùng Scanner để tách và phân tích token. Bọc thêm reader có bộ đệm có thể hữu ích ở tầng nguồn trong một số cấu hình, nhưng không biến công việc phân tích số thành một thao tác không có chi phí.

Ngược lại, `BufferedReader` chủ yếu cung cấp đọc ký tự/dòng có bộ đệm; nó không tự thay thế mọi quy tắc đọc số của Scanner. [Vai trò của BufferedReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedReader.html).

## 4. Chậm do CPU hay đang chờ I/O?

Một chương trình không trả kết quả ngay có thể đang:

1. Chờ người dùng hoặc nguồn mạng cung cấp dữ liệu.
2. Chờ dấu phân cách, kết thúc dòng hoặc EOF.
3. Phân tích rất nhiều token.
4. So khớp một biểu thức chính quy tốn công.
5. Chờ ghi log, cập nhật giao diện hoặc xử lý nghiệp vụ sau mỗi token.

Đổi Scanner sang cách đọc khác sẽ không tự sửa một bên gửi không bao giờ kết thúc bản tin. Cần biết thời gian đang đi đâu trước khi kết luận bộ phân tích là nút thắt.

Scanner có các phương thức đọc và kiểm tra có thể chặn; tên `hasNext()` không có nghĩa là phép kiểm tra không chờ. Khi làm việc với nguồn đang mở, cả tốc độ và điều kiện kết thúc bản tin đều cần được thiết kế.

Nếu chương trình liên tục in thông báo mà không tiêu thụ token, đó có thể là vòng lặp bận do logic sai, không phải tốc độ đọc của Scanner.

## 5. Đo hiệu năng sao cho kết luận có ý nghĩa

Trước tiên, xác định câu hỏi đo:

- Cần thời gian xử lý cả tệp từ đầu đến cuối hay chỉ thời gian phân tích nội dung đã nằm trong bộ nhớ?
- Cần thông lượng, thời gian phản hồi hay bộ nhớ đỉnh?
- Dữ liệu bình thường hay dữ liệu dài/xấu trong trường hợp biên?
- Chi phí mở nguồn, giải mã, kiểm tra lỗi và đóng tài nguyên có nằm trong phạm vi đo không?

Hai phép đo sau trả lời hai câu hỏi khác nhau:

~~~text
Đo toàn tuyến:
  mở nguồn -> giải mã -> phân tích -> kiểm tra -> xử lý -> đóng

Đo phần phân tích:
  nội dung đã có trong bộ nhớ -> phân tích -> trả kết quả
~~~

Nếu một bên được đo cả đọc đĩa còn bên kia chỉ đọc chuỗi trong RAM, kết quả không phải so sánh công bằng của bộ phân tích.

Một kế hoạch đo thực tế cần:

1. Tạo bộ dữ liệu đại diện cho kích thước token, tỷ lệ lỗi và quy ước số.
2. Xác nhận hai cách triển khai nhận cùng đầu vào và tạo cùng kết quả.
3. Tránh `println` bên trong vùng đo nếu mục tiêu là phân tích dữ liệu.
4. Tách bước chuẩn bị dữ liệu khỏi vùng đo khi câu hỏi chỉ nhắm đến parsing.
5. Có thời gian làm nóng JVM, nhiều lượt đo và nhiều lần khởi chạy phù hợp.
6. Dùng kết quả tính toán để tránh đo một đoạn mã không còn ý nghĩa thực thi.
7. Ghi rõ JDK, cấu hình JVM, dữ liệu và điều kiện chạy.
8. Khi cần, theo dõi cấp phát/GC và bộ nhớ thay vì chỉ nhìn thời gian.

JMH là công cụ của OpenJDK hỗ trợ xây dựng và chạy benchmark trên JVM. Nó phù hợp khi cần phép đo phần mã nhỏ có cấu hình rõ; vẫn phải thiết kế đúng dữ liệu và phép so sánh. [Dự án JMH](https://github.com/openjdk/jmh).

Một lần bấm giờ bằng `System.nanoTime()` có thể giúp quan sát thô, nhưng chưa đủ làm bằng chứng cho kết luận chung như “cách A luôn nhanh gấp 10”. Bài này không đưa ra tỷ lệ tốc độ vì chưa thực hiện benchmark trên một tải công việc được quy định.

## 6. Ví dụ thay thế chỉ đúng khi giữ rõ hợp đồng đầu vào

Giả sử tệp do ứng dụng kiểm soát có đúng **một số nguyên thập phân trên mỗi dòng**, không có khoảng trắng dư, không có dấu phân nhóm và không có dòng rỗng. Ta có thể đọc từng dòng bằng `BufferedReader` rồi dùng `Integer.parseInt(...)`.

Chương trình sau minh họa hai cách cho cùng tổng trên bộ dữ liệu hợp lệ. Nó còn cho thấy hai cách **không có cùng ngữ nghĩa trên mọi chuỗi đầu vào**.

Lưu thành `ScannerAlternativeDemo.java`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.Locale;
import java.util.Scanner;

public class ScannerAlternativeDemo {
    private static long scannerSum(String input) {
        try (Scanner scanner = new Scanner(input)) {
            scanner.useLocale(Locale.US);
            long total = 0;

            while (scanner.hasNext()) {
                if (!scanner.hasNextInt()) {
                    throw new IllegalArgumentException(
                            "Invalid int: " + scanner.next());
                }
                total = Math.addExact(total, scanner.nextInt());
            }
            return total;
        }
    }

    private static long lineReaderSum(String input) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(input))) {
            long total = 0;
            String line;

            while ((line = reader.readLine()) != null) {
                int value = Integer.parseInt(line);
                total = Math.addExact(total, value);
            }
            return total;
        }
    }

    public static void main(String[] args) throws IOException {
        String input = "10\n20\n-3\n";
        System.out.println("scanner=" + scannerSum(input));
        System.out.println("lineReader=" + lineReaderSum(input));

        System.out.println("scannerGrouped="
                + scannerSum("1,000\n"));

        try {
            lineReaderSum("1,000\n");
        } catch (NumberFormatException failure) {
            System.out.println(
                    "lineReaderGrouped=NumberFormatException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 ScannerAlternativeDemo.java
java ScannerAlternativeDemo
~~~

Stdout chính xác:

~~~text
scanner=27
lineReader=27
scannerGrouped=1000
lineReaderGrouped=NumberFormatException
~~~

Chương trình **không đo tốc độ**. Nó kiểm chứng tính đúng trên một trường hợp và chứng minh sự khác nhau của quy tắc nhận số:

- Scanner dùng locale US chấp nhận cách viết có dấu phân nhóm `1,000`.
- `Integer.parseInt` không nhận cách viết ấy.
- Scanner tách theo token khoảng trắng; bản đọc dòng đòi cả dòng là một số.
- Lỗi của `nextInt()` và `parseInt(...)` cũng không có cùng loại ngoại lệ.

Muốn thay thế trong một ứng dụng, phải chọn rõ tập đầu vào được chấp nhận, cách báo lỗi và cách kiểm tra trường thừa/thiếu. Cùng cho tổng đúng trên ba số chưa đủ chứng minh hai cách là tương đương.

Cách đọc dòng minh họa cũng không tự chứng minh nhanh hơn; nó chỉ có hợp đồng đơn giản hơn để có thể đo và đánh giá.

## 7. Giới hạn bộ nhớ: đọc dần không bảo đảm bộ nhớ luôn cố định

Scanner có thể đọc từ nguồn theo từng phần, nhưng một số thao tác cần tìm ranh giới chưa xuất hiện. Token hoặc dòng dài có thể làm dữ liệu giữ trong bộ đệm tăng lên.

Ví dụ:

- `nextLine()` trên nguồn rất dài không có xuống dòng cần tìm tới cuối dòng hoặc cuối nguồn.
- Một token khổng lồ chưa có dấu phân cách có thể yêu cầu đọc thêm.
- Tìm kiếm không giới hạn phù hợp có thể tiếp tục khảo sát dữ liệu lâu hơn dự kiến.

Tài liệu Scanner lưu ý `nextLine()` có thể đệm toàn bộ đầu vào khi không tìm được dấu kết thúc dòng; `findWithinHorizon(..., 0)` thực hiện tìm kiếm không bị giới hạn bởi horizon. Không dùng các thao tác đó như một cơ chế tự bảo vệ kích thước bản tin. [Các phương thức Scanner](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Scanner.html).

Ngoài bộ đệm của công cụ, ứng dụng còn có thể giữ tất cả token trong `List` hoặc đọc toàn bộ tệp bằng `Files.readString(...)`. Khi đó bộ nhớ tăng có thể do lựa chọn của chính ứng dụng.

Các giới hạn cần cân nhắc theo yêu cầu gồm tổng số byte, độ dài token/trường/dòng, số bản ghi và độ sâu cấu trúc. Chỉ kiểm tra độ dài sau khi đã nạp trọn một giá trị quá lớn có thể quá muộn cho mục tiêu bảo vệ bộ nhớ.

Đọc dòng bằng `BufferedReader.readLine()` cũng không tự tạo giới hạn chiều dài dòng. Đổi lớp đọc mà không thiết kế giới hạn vẫn có thể giữ nguyên vấn đề.

## 8. Vì sao dấu phân cách không phải ngữ pháp của định dạng?

Một dấu phân cách nói “tách ở những vị trí khớp mẫu này”. Một bộ phân tích định dạng còn cần hiểu **ngữ cảnh**:

- Dấu phẩy nằm trong hay ngoài chuỗi được trích dẫn?
- Dấu ngoặc hiện tại mở cấu trúc nào?
- Ký tự escape có làm ký tự tiếp theo mất vai trò đặc biệt không?
- Một trường vắng, một trường rỗng và giá trị `null` có khác nhau không?
- Đang đọc tên trường, giá trị hay ký hiệu kết thúc?
- Có trường bắt buộc, trường trùng hoặc trường không được phép không?

Scanner có thể là công cụ thành phần trong một bộ phân tích tự viết, nhưng `useDelimiter(...)` không tự cung cấp các quy tắc ấy. Khi tự bổ sung toàn bộ trạng thái, người viết đang xây một parser và phải chịu trách nhiệm kiểm chứng parser đó.

Không nên đồng nhất “tách được chuỗi mẫu” với “hỗ trợ định dạng”.

## 9. Thí nghiệm CSV: dấu phẩy trong ngoặc kép

Xét bản ghi:

~~~csv
1,"Nguyen, An",active
~~~

Theo quy ước CSV có trích dẫn, tên `Nguyen, An` là một trường. Bản ghi có ba trường về mặt ngữ nghĩa.

Nếu chỉ tách bằng dấu phẩy, Scanner không tự hiểu cặp ngoặc kép. Lưu thành `ScannerCsvLimitDemo.java`:

~~~java
import java.util.Scanner;

public class ScannerCsvLimitDemo {
    public static void main(String[] args) {
        String csv = "1,\"Nguyen, An\",active";

        try (Scanner scanner = new Scanner(csv)) {
            scanner.useDelimiter(",");
            int fields = 0;

            while (scanner.hasNext()) {
                fields++;
                System.out.println(fields
                        + ": [" + scanner.next() + "]");
            }

            System.out.println("tokens=" + fields);
        }
    }
}
~~~

~~~shell
javac --release 17 -encoding UTF-8 ScannerCsvLimitDemo.java
java ScannerCsvLimitDemo
~~~

Stdout chính xác:

~~~text
1: [1]
2: ["Nguyen]
3: [ An"]
4: [active]
tokens=4
~~~

Dấu ngoặc kép còn nguyên trong token và tên bị chia thành hai phần. Chương trình cho bốn token, trong khi bản ghi có ba trường mong đợi.

Đổi sang `String.split(",")` không tự sửa lỗi ngữ nghĩa này. Một biểu thức chính quy đặc chế cho vài ví dụ cũng cần được kiểm tra với ngoặc kép được escape, trường rỗng, xuống dòng trong trường được trích dẫn và bản ghi lỗi.

Với CSV thực tế, chọn parser hỗ trợ đúng biến thể CSV đầu vào. Chẳng hạn Apache Commons CSV có các cấu hình định dạng và xử lý trích dẫn/escape; phải chọn đúng quy ước thay vì coi mọi tệp đuôi `.csv` có cùng luật. [Tài liệu Apache Commons CSV](https://commons.apache.org/proper/commons-csv/apidocs/index.html).

## 10. JSON, XML và cấu trúc lồng nhau

Với JSON:

~~~json
{
  "name": "A,B",
  "items": [
    {"id": 1},
    {"id": 2}
  ]
}
~~~

Dấu phẩy trong `"A,B"` là nội dung chuỗi, còn các dấu phẩy khác phân cách thành phần của cấu trúc. Chỉ tách theo dấu phẩy, dấu hai chấm hoặc ngoặc không đủ giữ thông tin ngữ cảnh.

Một parser còn phải nhận diện chuỗi có escape, kiểu số, boolean, `null`, mảng và đối tượng; sau đó ứng dụng vẫn phải kiểm tra cấu trúc dữ liệu mong đợi. Đọc thành công cú pháp không chứng minh các trường nghiệp vụ đã hợp lệ.

Với XML, thẻ, thuộc tính, nội dung văn bản, namespace và các quy tắc cú pháp cũng không tương đương một tập dấu phân cách Scanner.

Khi định dạng có parser chuyên dụng, dùng nó theo yêu cầu xử lý: đọc theo sự kiện/dòng token khi cần xử lý dần, hoặc xây mô hình đối tượng khi phù hợp kích thước và cách truy cập. Không cần nạp toàn bộ tài liệu chỉ vì định dạng phức tạp; lựa chọn chế độ đọc cũng là một quyết định kiến trúc.

Bài không xây parser JSON/XML bằng regex và không cung cấp một đoạn tách chuỗi được gắn nhãn “parser đầy đủ”.

## 11. Chọn công cụ theo hợp đồng dữ liệu

| Yêu cầu | Hướng tiếp cận thường phù hợp | Điều vẫn phải kiểm tra |
| --- | --- | --- |
| Vài token hoặc số nhập từ CLI | Scanner | Vòng đời nguồn, sai kiểu và điều kiện dừng |
| Văn bản theo dòng, quy tắc chuyển kiểu đơn giản | BufferedReader hoặc API đọc dòng phù hợp | Độ dài dòng, trường thiếu/thừa và lỗi chuyển đổi |
| Tệp token lớn, đã đo Scanner là nút thắt | Cách đọc/chuyển đổi chuyên biệt cho ngữ pháp đã chốt | Tương đương hành vi và lợi ích đo được |
| CSV có quote/escape/trường nhiều dòng | Parser CSV theo đúng biến thể | Cấu hình trích dẫn, trường rỗng và bản ghi lỗi |
| JSON/XML có cấu trúc | Parser của định dạng | Giới hạn kích thước/độ sâu và kiểm tra dữ liệu |
| Giao thức nhị phân | API/parser theo đặc tả nhị phân | Độ dài, byte order, framing và lỗi truyền |

Không tự viết bộ đọc byte cực nhanh cho một bài toán nhỏ chỉ vì nghe nói Scanner chậm. Mã chuyên biệt phải xử lý dấu, tràn số, kết thúc nguồn, encoding và dữ liệu lỗi; bỏ các kiểm tra đó chỉ làm phép so sánh nhẹ việc hơn.

Cũng không giữ Scanner chỉ vì nó chạy được trên dữ liệu mẫu nếu định dạng đòi hỗ trợ đầy đủ cấu trúc mà đoạn mã chưa xử lý.

## 12. Cải thiện trong phạm vi dùng Scanner

Nếu hợp đồng đầu vào vẫn đơn giản và Scanner vẫn phù hợp:

1. Duy trì một scanner cho một nguồn liên tục, tránh khởi tạo mới cho từng token.
2. Đặt locale, cơ số và dấu phân cách một lần ở nơi cấu hình khi chúng không cần thay đổi.
3. Dùng mẫu phân cách đơn giản đúng yêu cầu; tránh mẫu phức tạp chỉ để đoán nhiều định dạng khác nhau.
4. Xử lý token sai có chủ đích, không bắt lỗi rồi lặp lại mãi ở cùng token.
5. Không giữ mọi token trong bộ nhớ nếu yêu cầu chỉ cần xử lý tuần tự.
6. Tách log/xử lý nghiệp vụ khỏi phân tích để biết phần nào thực sự tốn thời gian.
7. Kiểm tra lỗi đọc nguồn khi cần xác nhận đã xử lý toàn bộ dữ liệu.
8. Chỉ thay kiến trúc sau khi biết yêu cầu đúng định dạng và nút thắt thực tế.

“Duy trì một scanner” không có nghĩa chia sẻ nó tùy tiện giữa nhiều luồng. Scanner không tự an toàn cho việc dùng đồng thời; tổ chức một nơi sở hữu lượt đọc hoặc có đồng bộ thích hợp.

Không đóng một scanner bọc nguồn dùng chung chỉ để “giải phóng sau mỗi token”, vì việc đóng có thể truyền xuống nguồn. Tối ưu phải giữ đúng vòng đời tài nguyên.

## 13. Tự thực hành

1. Thêm đầu vào `"10 20\n"` cho hai hàm tính tổng trong ví dụ. Chỉ ra cách nào chấp nhận và hợp đồng nào đã bị thay đổi.
2. Cho ví dụ CSV nhận tên có dấu ngoặc kép được escape và một trường chứa xuống dòng. Liệt kê các quy tắc mà dấu phân cách `","` chưa thể hiện.
3. Thiết kế một phép đo chỉ phần phân tích số: dữ liệu chuẩn bị ở đâu, kết quả được sử dụng thế nào và những công việc nào bị loại khỏi vùng đo?
4. Thiết kế phép đo cả tệp từ đầu đến cuối. Giải thích vì sao kết quả này có thể khác kết quả đọc chuỗi trong RAM.
5. Chọn một đầu vào có token cực dài. Nêu giới hạn cần thực hiện trước khi giữ toàn bộ token, thay vì chỉ đổi Scanner thành đọc dòng.
6. Với một công cụ CLI đọc năm số mỗi lần chạy, quyết định nên ưu tiên điểm nào: hợp đồng đầu vào, báo lỗi, khả năng đọc mã hay một tỷ lệ tốc độ chưa được đo.

Một lựa chọn đúng cần đồng thời giữ được **ngữ nghĩa đầu vào**, **giới hạn tài nguyên** và **mức hiệu năng được kiểm chứng cho nhiệm vụ thực tế**.
