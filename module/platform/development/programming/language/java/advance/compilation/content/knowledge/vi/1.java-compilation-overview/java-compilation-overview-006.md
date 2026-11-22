# Mã biên dịch thành công chưa bảo đảm chạy đúng

Khi `javac` kết thúc với mã thoát thành công, điều được xác nhận là **mã nguồn đã vượt qua những kiểm tra mà trình biên dịch thực hiện trong cấu hình hiện tại và đã tạo được đầu ra biên dịch tương ứng**. Đó là một cột mốc rất quan trọng, nhưng còn cách xa kết luận “chương trình chắc chắn chạy được, chạy ổn định và trả kết quả đúng”.

Một chương trình có thể:

- **Không khởi động được** vì thiếu lớp phụ thuộc hoặc dùng phiên bản Java không tương thích.
- **Khởi động được nhưng dừng giữa chừng** vì dữ liệu sai, chia cho không, thiếu tệp, mạng bị ngắt hoặc tài nguyên cạn.
- **Chạy đến cuối và in kết quả** nhưng kết quả sai quy tắc nghiệp vụ.
- **Cho kết quả đúng ở một lần thử** nhưng sai khi thay đổi dữ liệu, môi trường, thứ tự thực thi hoặc có nhiều luồng đồng thời.

Bài này giúp nhận biết mỗi tình huống, hiểu vì sao trình biên dịch không thể bảo đảm thay cho việc chạy thử và kiểm chứng, đồng thời thiết kế quy trình giảm rủi ro.

## 1. “Biên dịch thành công” thực sự xác nhận điều gì?

Với cách biên dịch Java thông thường:

~~~text
Mã nguồn .java
    |
    | javac: phân tích cú pháp, phân giải tên/kiểu, kiểm tra
    | nhiều quy tắc ngôn ngữ, phát sinh bytecode
    v
Tệp .class đã tạo được
    |
    | java: nạp lớp, liên kết, khởi tạo, chạy main
    v
Chương trình thực thi
    |
    | dữ liệu, phụ thuộc, hệ điều hành, mạng, người dùng...
    v
Hành vi quan sát được
    |
    | so với yêu cầu và trường hợp kiểm thử
    v
Kết luận về tính đúng đắn trong phạm vi đã kiểm chứng
~~~

`javac` thường phát hiện các vấn đề như sai cú pháp, dùng biến chưa khai báo, gán kiểu không tương thích hoặc gọi phương thức không khớp chữ ký đã biết khi biên dịch. Nhưng nó **không thực thi mọi dòng lệnh, không biết đầy đủ dữ liệu sẽ nhận được và không suy ra ý định nghiệp vụ của con người**.

Cần phân biệt bốn kết luận khác nhau:

| Kết luận | Bằng chứng tối thiểu | Điều chưa được bảo đảm |
| --- | --- | --- |
| Biên dịch thành công | Lệnh `javac` kết thúc thành công; đầu ra phù hợp | Chạy được trên môi trường đích |
| Khởi động thành công | Runtime tìm và nạp được thành phần cần thiết để bắt đầu | Mọi đường thực thi sau đó đều an toàn |
| Một lần chạy thành công | Chương trình không lỗi trong lần chạy cụ thể | Kết quả đúng với yêu cầu, mọi đầu vào khác đều đúng |
| Kiểm chứng đạt yêu cầu | Bài kiểm thử/đối chiếu với tiêu chí được xác định cho phạm vi cụ thể | Không còn bất kỳ lỗi nào trong mọi tình huống có thể xảy ra |

**Không có suy luận hợp lệ rằng “build xanh ⇒ chất lượng đúng tuyệt đối”.** Build xanh thường cho thấy một tập kiểm tra đã vượt qua; độ tin cậy phụ thuộc các kiểm tra đó thực sự bao phủ điều gì.

## 2. Ví dụ một: mã hợp lệ nhưng tính tiền sai

Xét yêu cầu: tổng tiền thanh toán bằng **đơn giá nhân số lượng, rồi cộng phí vận chuyển**. Hãy lưu mã độc lập sau thành **`OrderBill.java`**:

~~~java
public class OrderBill {
    public static void main(String[] args) {
        int unitPrice = 19_000;
        int quantity = 3;
        int deliveryFee = 2_500;

        // Sai yêu cầu: cần cộng phí, nhưng lại trừ phí.
        int payable = unitPrice * quantity - deliveryFee;

        System.out.println("Tiền phải trả: " + payable);
    }
}
~~~

Tại thư mục chứa tệp:

~~~sh
javac -encoding UTF-8 OrderBill.java
java OrderBill
~~~

Chương trình chạy bình thường và in:

~~~text
Tiền phải trả: 54500
~~~

Tuy nhiên, kết quả đúng theo yêu cầu là `19_000 × 3 + 2_500 = 59_500`, tức `59500`. Lỗi nằm ở **ý nghĩa của công thức**, trong khi dấu trừ vẫn hoàn toàn hợp lệ về cú pháp và kiểu. `javac` không có tài liệu nghiệp vụ để hiểu rằng phí vận chuyển cần được cộng.

Sửa dòng tính tiền thành:

~~~java
int payable = unitPrice * quantity + deliveryFee;
~~~

Sau khi **biên dịch lại** rồi chạy `java OrderBill`, stdout mới là:

~~~text
Tiền phải trả: 59500
~~~

Đây là **lỗi logic (logic bug)**: mã compile, ứng dụng chạy, vẫn trả lời sai. Nó thường nguy hiểm hơn lỗi biên dịch rõ ràng vì rất dễ lọt qua nếu chỉ quan sát rằng ứng dụng không báo exception.

### Bài học từ lỗi logic

- Đề bài phải có **kết quả kỳ vọng độc lập với cách viết mã**. Nếu kiểm thử chỉ sao chép lại cùng công thức sai, bài kiểm thử cũng sẽ “đúng” một cách giả tạo.
- Các quy tắc như giảm giá, thuế, phí, làm tròn, giới hạn số lượng cần thể hiện thành ví dụ đầu vào/đầu ra và điều kiện biên.
- Chạy một ví dụ đơn giản chưa đủ: nhiều lỗi chỉ xuất hiện ở giá trị 0, giá trị âm, số rất lớn, đơn hàng rỗng, hoặc các nhánh xử lý khác.

## 3. Ví dụ hai: biên dịch được nhưng lỗi chỉ xuất hiện khi chạy

Lưu mã độc lập sau thành **`ShareCalculator.java`**:

~~~java
public class ShareCalculator {
    public static void main(String[] args) {
        int total = 120;
        int people = Integer.parseInt(args[0]);
        int perPerson = total / people;

        System.out.println("Mỗi người nhận: " + perPerson);
    }
}
~~~

Biên dịch:

~~~sh
javac ShareCalculator.java
~~~

Chạy với dữ liệu hợp lệ:

~~~sh
java ShareCalculator 4
~~~

Đầu ra:

~~~text
Mỗi người nhận: 30
~~~

Bây giờ thử từng đầu vào khác:

~~~sh
java ShareCalculator 0
java ShareCalculator abc
java ShareCalculator
~~~

Những lần chạy này thất bại theo các nguyên nhân khác nhau:

| Đầu vào | Vấn đề | Dạng lỗi khi chạy |
| --- | --- | --- |
| `4` | Hợp lệ | In `Mỗi người nhận: 30` |
| `0` | Chia số nguyên cho 0 | `ArithmeticException` |
| `abc` | Chuỗi không biểu diễn số nguyên hợp lệ | `NumberFormatException` |
| Không có tham số | Truy cập `args[0]` dù mảng rỗng | `ArrayIndexOutOfBoundsException` |

Bảng nêu **loại exception** thay vì chép nguyên stack trace, vì đường dẫn tệp, số dòng và cách hiển thị phụ thuộc môi trường. Mọi trường hợp trên đều xuất phát từ **cùng một tệp `.class` đã biên dịch thành công**.

`javac` biết `args` có kiểu `String[]` và `Integer.parseInt` nhận một `String`. Nhưng nó không biết người dùng sẽ cung cấp bao nhiêu đối số, chuỗi gì, hoặc số nguyên có bằng 0 hay không. Những ràng buộc này chỉ được xác định khi chạy.

### Phiên bản có kiểm tra đầu vào

Ta có thể biến những tình huống không hợp lệ thành thông báo có chủ đích. Lưu phiên bản hoàn chỉnh sau vào **`SafeShareCalculator.java`**:

~~~java
public class SafeShareCalculator {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.out.println("Cần đúng một số người.");
            return;
        }

        int people;
        try {
            people = Integer.parseInt(args[0]);
        } catch (NumberFormatException ex) {
            System.out.println("Số người phải là số nguyên.");
            return;
        }

        if (people <= 0) {
            System.out.println("Số người phải lớn hơn 0.");
            return;
        }

        int perPerson = 120 / people;
        System.out.println("Mỗi người nhận: " + perPerson);
    }
}
~~~

~~~sh
javac -encoding UTF-8 SafeShareCalculator.java
java SafeShareCalculator 4
java SafeShareCalculator 0
java SafeShareCalculator abc
java SafeShareCalculator
~~~

Lần lượt mỗi lệnh `java` in đúng một dòng:

~~~text
Mỗi người nhận: 30
Số người phải lớn hơn 0.
Số người phải là số nguyên.
Cần đúng một số người.
~~~

Chương trình này giải quyết rủi ro **đã xác định**: thiếu tham số, chuỗi không thể chuyển thành số và giá trị không dương. Nó vẫn chưa quy định chính sách xử lý phần dư khi `120` không chia hết cho số người hoặc có yêu cầu làm tròn theo nghiệp vụ. **Xử lý exception không thay thế việc hiểu yêu cầu**.

## 4. Ví dụ ba: tương thích biên dịch không đồng nghĩa tương thích môi trường chạy

Một chương trình có thể tạo ra bytecode hợp lệ trên máy phát triển nhưng không chạy được trên máy đích.

### Khác phiên bản JDK/JVM

Tệp `.class` có thông tin phiên bản định dạng. Ví dụ:

- Java 17 thường phát sinh classfile major version **61**.
- Java 21 thường phát sinh classfile major version **65**.

Nếu biên dịch bằng mục tiêu Java 21 rồi chuyển tệp lớp sang một runtime Java 17, JVM Java 17 không hiểu định dạng mới và có thể báo `UnsupportedClassVersionError`. Thông báo này thường xuất hiện khi tải lớp, **không phải lúc `javac` đã chạy thành công trên máy phát triển**.

Khi cần triển khai trên Java 17 và đang dùng JDK mới hơn có hỗ trợ mục tiêu đó, hãy thử:

~~~sh
javac --release 17 OrderBill.java
~~~

`--release 17` ràng buộc mức ngôn ngữ, định dạng bytecode và tập API nền tảng Java mà compiler cho phép tham chiếu theo target. Cách này đáng tin hơn việc chỉ thiết lập `-source` và `-target` riêng lẻ khi muốn dùng API chuẩn tương thích. Tuy nhiên, **nó không tự bảo đảm thư viện bên thứ ba, cấu hình, bản vá hoặc môi trường runtime tương thích**.

Dùng các lệnh:

~~~sh
javac -version
java -version
javap -verbose OrderBill
~~~

để kiểm tra phiên bản compiler/runtime và chi tiết classfile (tìm trường `major version` trong đầu ra của `javap -verbose`). Không suy đoán runtime đích chỉ từ JDK trên máy viết mã.

### Thiếu lớp hoặc thư viện khi chạy

Một dự án có thể biên dịch khi thư viện được đặt trên **compile classpath**, nhưng lúc chạy thiếu JAR tương ứng trên **runtime classpath**. Khi JVM cần nạp hoặc liên kết thành phần còn thiếu, chương trình có thể gặp `NoClassDefFoundError` hay lỗi nạp/l iên kết liên quan. `ClassNotFoundException` thường được quan sát khi mã tìm tải lớp động bằng API như `Class.forName`.

Ví dụ, mã gọi một thư viện có mặt ở máy build chưa chắc tìm được thư viện đó sau khi copy riêng tệp `.class` sang máy chạy. Cần quản lý dependency và đóng gói nhất quán, thay vì xem lỗi của lớp còn thiếu là bằng chứng rằng compiler đã kiểm tra sai.

Một số lỗi tương thích nhị phân còn tinh vi hơn: mã đã compile với phiên bản A của thư viện, nhưng runtime dùng phiên bản B thay đổi chữ ký hoặc hành vi phương thức. Lúc gọi tới thành phần đó, có thể gặp các lỗi liên kết như `NoSuchMethodError` hoặc nhận kết quả khác với kỳ vọng. **Kiểm thử trong môi trường có dependencies thực tế** mới phát hiện được các vấn đề này.

## 5. Các nhóm vấn đề còn lại sau khi compile

| Nhóm | Ví dụ cụ thể | Vì sao `javac` chưa đủ? | Cách kiểm chứng |
| --- | --- | --- | --- |
| Dữ liệu đầu vào | Số 0, chuỗi hỏng, trường bắt buộc thiếu | Dữ liệu thực chỉ xuất hiện khi chạy | Validation và kiểm thử biên |
| Logic nghiệp vụ | Trừ phí thay vì cộng | Compiler không biết quy tắc tiền phải trả | Ví dụ kết quả kỳ vọng, unit test |
| Phụ thuộc runtime | Thiếu JAR, sai phiên bản lớp | Compile và runtime có thể dùng môi trường khác | Chạy artifact đã đóng gói trên môi trường đích |
| I/O và tài nguyên | Không tìm thấy file, hết quyền ghi, ổ đĩa đầy | Tệp/hệ thống file thay đổi khi chạy | Integration test và xử lý lỗi I/O |
| Mạng và dịch vụ ngoài | Timeout, kết nối bị từ chối, dữ liệu API khác | Không biết trạng thái mạng và dịch vụ trong tương lai | Test tích hợp, timeout, retry có kiểm soát |
| Đồng thời | Hai luồng cập nhật cùng trạng thái không an toàn | Kiểm tra kiểu không chứng minh không có race condition | Thiết kế đồng bộ, kiểm thử tải/concurrency |
| Bộ nhớ, hiệu năng | `OutOfMemoryError`, xử lý mất quá lâu | Tiêu thụ tài nguyên phụ thuộc quy mô dữ liệu và runtime | Test tải, đo bộ nhớ, profiling |
| Bảo mật | Quyền truy cập thiếu kiểm soát, lộ dữ liệu | Mã đúng cú pháp vẫn có thể có lỗ hổng | Security review, test phân quyền và dữ liệu |
| Triển khai | Biến môi trường sai, cổng bận, timezone khác | Điều kiện vận hành không nằm trong kiểm tra tĩnh | Smoke test, monitoring, cấu hình môi trường |
| Tính ổn định | Một test qua, nhiều lần khác sai | Lỗi phụ thuộc thời điểm, dữ liệu hoặc môi trường | Test lặp lại có chủ đích, thu thập log |

Không nên quy tất cả các lỗi này thành “lỗi biên dịch”. Cách phân loại đúng giúp xác định ai cần kiểm tra gì: người viết mã, người cấu hình build, người vận hành hay người xác nhận yêu cầu.

### Một số tình huống dễ đánh giá sai

**Exception được bắt không đồng nghĩa nghiệp vụ thành công.** Nếu chương trình bắt mọi `Exception` rồi trả về giá trị mặc định, hệ thống có thể không crash nhưng vẫn xuất kết quả sai. Cần quyết định khi nào được fallback và làm sao báo lỗi có ý nghĩa.

**Chạy hết `main` không đồng nghĩa đã xử lý thành công.** Lời gọi API có thể thất bại nhưng mã vẫn trả exit code 0; file xuất ra có thể thiếu dữ liệu; giao dịch có thể bị rollback. Cần kiểm tra hiệu ứng đầu ra đúng mong đợi, không chỉ trạng thái process.

**Không thấy exception không có nghĩa không có lỗi.** Một phép cộng số nguyên có thể bị tràn mà không ném exception mặc định; một quy tắc so sánh có thể sai nhưng vẫn trả `true`/`false` hợp lệ.

**Đơn vị đo và định dạng đầu vào có thể làm kết quả khác.** Tính bằng mili giây trong khi yêu cầu là giây; làm tròn tiền quá sớm; dùng dấu phẩy/dấu chấm số khác locale — tất cả đều có thể biên dịch và chạy.

## 6. Ví dụ bốn: tràn số nguyên vẫn có thể cho ra một giá trị

Lưu thành **`OverflowExample.java`**:

~~~java
public class OverflowExample {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        int wrapped = max + 1;

        System.out.println("Giá trị tính được: " + wrapped);
        System.out.println("Giá trị lớn nhất của int: " + max);
    }
}
~~~

~~~sh
javac OverflowExample.java
java OverflowExample
~~~

Stdout chính xác:

~~~text
Giá trị tính được: -2147483648
Giá trị lớn nhất của int: 2147483647
~~~

Kiểu `int` có giới hạn 32 bit có dấu. Phép cộng `Integer.MAX_VALUE + 1` bị tràn và quay vòng theo quy tắc số nguyên Java; `javac` chấp nhận chương trình và JVM không tự động ném exception ở phép cộng `int` thông thường. Nếu nghiệp vụ yêu cầu phát hiện tràn, có thể dùng `Math.addExact` hoặc kiểu biểu diễn/ràng buộc khác phù hợp.

Phiên bản kiểm tra tràn, lưu thành **`CheckedAddition.java`**:

~~~java
public class CheckedAddition {
    public static void main(String[] args) {
        try {
            int result = Math.addExact(Integer.MAX_VALUE, 1);
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("Phát hiện tràn số nguyên.");
        }
    }
}
~~~

~~~sh
javac -encoding UTF-8 CheckedAddition.java
java CheckedAddition
~~~

Kết quả:

~~~text
Phát hiện tràn số nguyên.
~~~

Trong xử lý tiền tệ, còn phải quan tâm đơn vị, scale, làm tròn và nghiệp vụ; `Math.addExact` chỉ giải quyết rủi ro tràn của phép cộng số nguyên, **không tự sửa mọi lỗi tính tiền**.

## 7. Kiểm thử có thể phát hiện lỗi logic mà compiler bỏ qua

Để tách **hành vi muốn có** khỏi **hành vi mã tạo ra**, hãy viết hàm có hợp đồng rõ và kiểm thử các ví dụ đại diện. Tạo **`OrderPolicyTest.java`**, một chương trình tự kiểm tra độc lập chỉ dùng Java chuẩn:

~~~java
public class OrderPolicyTest {
    static int amountToPay(int unitPrice, int quantity, int deliveryFee) {
        return unitPrice * quantity + deliveryFee;
    }

    static void check(String name, int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(
                    name + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        check("don mot san pham", 21_500, amountToPay(19_000, 1, 2_500));
        check("don ba san pham", 59_500, amountToPay(19_000, 3, 2_500));
        check("mien phi van chuyen", 38_000, amountToPay(19_000, 2, 0));
        check("khong mua san pham", 2_500, amountToPay(19_000, 0, 2_500));
    }
}
~~~

~~~sh
javac -encoding UTF-8 OrderPolicyTest.java
java OrderPolicyTest
~~~

Kết quả khi bốn kỳ vọng đều khớp:

~~~text
PASS don mot san pham
PASS don ba san pham
PASS mien phi van chuyen
PASS khong mua san pham
~~~

Mỗi `check` đối chiếu kết quả thực tế với **giá trị kỳ vọng tính từ yêu cầu**, không chỉ xác nhận hàm trả về một số. Nếu thay phép cộng `deliveryFee` trong `amountToPay` bằng phép trừ, chương trình vẫn biên dịch, nhưng bài kiểm tra đầu tiên ném `AssertionError`: đó là lỗi được phát hiện ở **bước kiểm thử**, không phải trong `javac`.

Trong dự án thật, các kiểm thử như vậy thường được tổ chức bằng JUnit và chạy qua Gradle/Maven; ví dụ ở đây dùng `main` để học viên có thể chạy bằng JDK thuần, không cần thêm dependency.

### Thiết kế bộ kiểm thử có ý nghĩa

1. **Trường hợp thông thường:** Giá trị hay xảy ra; kết quả có thể tính độc lập.
2. **Ranh giới:** 0, một phần tử, giá trị tối đa/tối thiểu hoặc ngay sát ngưỡng theo hợp đồng.
3. **Dữ liệu không hợp lệ:** Thiếu trường, sai định dạng, giá trị trái quy tắc; kiểm tra chương trình từ chối rõ ràng.
4. **Lỗi môi trường:** Mất kết nối, tệp không tồn tại, thiếu quyền, phụ thuộc không sẵn sàng.
5. **Tương tác và đồng thời:** Dữ liệu được cập nhật trong lúc xử lý, hai yêu cầu cùng thay đổi một tài nguyên.
6. **Hồi quy:** Lỗi đã sửa được giữ lại dưới dạng test để không vô tình tái xuất hiện.

Không cần ép mọi dự án có cùng số lượng test. Mỗi bài kiểm thử nên trả lời câu hỏi cụ thể: *lỗi nào có thể xảy ra mà compiler không phát hiện, và bằng chứng nào cho thấy hành vi mong muốn đang được giữ?*

## 8. Các tầng kiểm chứng sau khi biên dịch

Một quy trình điển hình:

~~~text
Mã nguồn + hợp đồng hành vi
           |
           v
Compile / static checks
           |  sai cú pháp/kiểu? -> sửa mã
           v
Unit tests
           |  sai nghiệp vụ trong phạm vi nhỏ? -> sửa logic
           v
Integration tests
           |  sai dependency / database / API? -> sửa cấu hình, tích hợp
           v
Packaging + chạy artifact thực tế
           |  JVM, JAR, classpath, config khớp?
           v
Smoke tests / end-to-end tests
           |  luồng quan trọng hoạt động?
           v
Theo dõi khi vận hành
           |  log, metrics, cảnh báo, kiểm soát lỗi
           v
Phản hồi và sửa lỗi có kiểm chứng
~~~

### Vai trò của từng tầng

| Tầng | Mục đích | Giới hạn |
| --- | --- | --- |
| Compiler/kiểm tra tĩnh | Loại lỗi ngôn ngữ, kiểu và một số vấn đề phát hiện không cần chạy | Không chứng minh nghiệp vụ hay môi trường runtime |
| Unit test | So sánh hàm/đơn vị nhỏ với yêu cầu | Có thể bỏ sót tương tác giữa thành phần |
| Integration test | Kiểm tra kết nối thật hoặc mô phỏng đủ sát giữa các thành phần | Không bảo đảm mọi cấu hình sản xuất |
| Smoke/end-to-end | Xác minh luồng chính qua artifact và môi trường gần thực tế | Thường ít bao phủ các nhánh chi tiết |
| Kiểm thử tải, bảo mật, độ bền | Kiểm tra rủi ro ngoài đường chạy thông thường | Cần thiết kế theo nhu cầu, không được suy luận từ build xanh |
| Quan sát runtime | Phát hiện hành vi bất thường với dữ liệu và tải thực | Phát hiện sau triển khai; không tự sửa lỗi |

**Không một tầng đơn lẻ nào thay thế tất cả tầng khác.** Chẳng hạn, unit test có thể cho thấy hàm tính tiền đúng, nhưng khi triển khai với currency/locale hoặc dữ liệu ngoài khác, hệ thống vẫn sai. Ngược lại, một bài end-to-end qua được có thể không chạm tới biên nhập liệu khiến chương trình crash.

### Kiểm tra đúng artifact

Một lỗi quy trình là kiểm thử thư mục build A, nhưng triển khai một JAR khác hoặc dùng dependency mới hơn. Để kết luận từ kiểm thử có giá trị:

- Xác định chính xác mã nguồn, tham số build, phiên bản JDK, dependencies và artifact đã kiểm thử.
- Nếu cần, dùng cùng artifact (hoặc artifact có thể tái lập đã xác minh) cho môi trường tiếp theo.
- Chạy ít nhất các thao tác quan trọng trên **môi trường gần điều kiện triển khai**.
- Nếu một lần build lỗi nhưng còn `.class`/JAR cũ, không được lấy việc artifact cũ vẫn chạy làm bằng chứng mã nguồn mới hợp lệ.

## 9. Đọc triệu chứng để tìm đúng loại lỗi

Giả sử gặp một vấn đề, có thể chẩn đoán theo chuỗi sau.

### Trường hợp A: `javac` báo lỗi và không tạo đầu ra mới như mong muốn

Hãy kiểm tra thông báo về cú pháp, import, tên lớp, visibility, type mismatch, method signature. Đây thường là lỗi liên quan **biên dịch**; xử lý trước khi mong đợi code mới chạy.

### Trường hợp B: `javac` thành công nhưng `java` chưa vào được luồng chính

Kiểm tra tên lớp fully-qualified, classpath/module path, có phương thức `main` phù hợp, các JAR phụ thuộc, phiên bản JVM. Ví dụ `Could not find or load main class` là vấn đề tìm/nạp lớp hoặc cấu hình chạy; `UnsupportedClassVersionError` gợi ý classfile mới hơn JVM đích.

### Trường hợp C: Chạy được một đoạn rồi xuất hiện exception

Đọc loại exception, stack trace và điều kiện thực thi. Ghi nhận **đầu vào và trạng thái môi trường tối thiểu có thể tái hiện**. Phân biệt lỗi dữ liệu (chẳng hạn `NumberFormatException`), phép toán (`ArithmeticException`) và lỗi truy cập tài nguyên (`IOException`). Không giấu stack trace hoặc gộp mọi lỗi vào một thông báo “unknown error” khi điều tra.

### Trường hợp D: Không có exception nhưng trả kết quả sai

Kiểm tra yêu cầu, giá trị trung gian, đơn vị đo, điều kiện nhánh và kết quả mong muốn độc lập. Viết một test tối giản tái hiện lỗi. Không bắt đầu bằng cách tăng timeout hoặc đổi cấu hình JVM nếu vấn đề thực sự nằm ở logic.

### Trường hợp E: Chỉ lỗi ở production hoặc dưới tải

So sánh JDK, artifact, classpath, biến môi trường, kết nối, permission, bộ nhớ, timezone, locale, lưu lượng và cấu hình luồng. Thu thập bằng chứng có dấu thời gian, dữ liệu đã che thông tin nhạy cảm và hướng tái hiện. Kết luận “máy tôi chạy được” chỉ nói về **một môi trường**, không phủ định lỗi ở môi trường khác.

## 10. Phạm vi và giới hạn cần ghi nhớ

- **Trình biên dịch không phải người kiểm thử nghiệp vụ.** Nó không có lời giải chuẩn cho bài toán tiền, thời hạn, phân quyền hay tình huống khách hàng.
- **Hệ thống kiểu không loại được mọi lỗi.** Một giá trị `int` hợp lệ về kiểu vẫn có thể không hợp lệ về miền nghiệp vụ, ví dụ số người bằng 0.
- **Trình biên dịch không kiểm tra trước mọi trạng thái runtime.** Tệp bị xóa, mạng ngắt, dịch vụ không phản hồi hay tài nguyên cạn là điều kiện có thể thay đổi sau khi build.
- **Bytecode verification trong JVM khác `javac`.** JVM có các quy tắc xác minh/kiểm tra liên kết riêng để bảo vệ tính hợp lệ của mã được nạp; điều này cũng không chứng minh kết quả nghiệp vụ đúng.
- **Static analyzer, test và review hỗ trợ nhau.** Các công cụ phân tích sâu hơn compiler có thể cảnh báo thêm mẫu lỗi, nhưng mọi lời cảnh báo và kết luận đều có phạm vi và giới hạn.
- **Không thể suy ra “đã hết lỗi” từ việc tất cả test hiện tại đều xanh.** Test chỉ bao phủ các tình huống/thuộc tính đã được xác định và thực thi; thêm test có ý nghĩa khi xuất hiện yêu cầu hoặc rủi ro mới.

## 11. Bài thực hành củng cố

**Bài 1 — Kiểm chứng lỗi logic.** Chạy `OrderBill.java`, ghi lại kết quả máy in và kết quả đúng theo yêu cầu. Chỉ ra vì sao cả hai kết quả đều có thể đi qua `javac` và điều chỉnh công thức.

**Bài 2 — Dữ liệu và thời điểm lỗi.** Chạy `ShareCalculator.java` với các tham số `4`, `0`, `abc` và không truyền gì. Lập bảng cho biết trường hợp nào kết thúc bình thường, trường hợp nào ném exception và nguyên nhân từ dữ liệu.

**Bài 3 — Ranh giới kiểm tra đầu vào.** Thử `SafeShareCalculator.java` với `4`, `0`, `abc`, không đối số và `7`. Với `7`, kết quả chia nguyên là `17` và còn dư `1`; hãy xác định yêu cầu nào phải bổ sung nếu nghiệp vụ không cho phép làm mất phần dư.

**Bài 4 — Kiểm thử trước khi sửa.** Thay phép cộng bằng phép trừ trong hàm `amountToPay` của `OrderPolicyTest.java`; dự đoán test nào lỗi trước. Chạy và quan sát `AssertionError` rồi sửa lại.

**Bài 5 — Triển khai.** Cho biết bạn sẽ kiểm tra gì nếu file `.class` được biên dịch bằng Java 21 nhưng máy chạy chỉ có Java 17; phân biệt sửa code, cấu hình `--release` và nâng runtime khi phù hợp.

### Tự kiểm tra

1. Vì sao `javac` chấp nhận công thức trừ phí vận chuyển dù kết quả sai? — Vì toán tử và kiểu hợp lệ, còn quy tắc phải cộng phí nằm ngoài kiểm tra tĩnh.
2. Nếu `java ShareCalculator 0` ném `ArithmeticException`, có phải `javac` đã thất bại? — Không; lỗi xảy ra trong quá trình chạy với dữ liệu 0.
3. Vì sao JAR chạy trên máy lập trình nhưng không chạy trên máy khác? — Có thể khác JVM, classpath, dependencies, cấu hình hoặc tài nguyên.
4. Tại sao cần biết giá trị *mong đợi* trong test? — Để đối chiếu với hành vi đúng theo yêu cầu, tránh chỉ xác nhận chương trình có trả về kết quả nào đó.
5. Thế nào là bằng chứng mạnh hơn “compile success”? — Kết hợp kiểm thử theo hợp đồng, kiểm tra môi trường triển khai, đo và quan sát hành vi thật trong phạm vi cần bảo đảm.

**Điểm cốt lõi:** `javac` trả lời câu hỏi *“Mã có hợp lệ theo các quy tắc biên dịch đã áp dụng và tạo được đầu ra không?”*. Việc chạy thử và kiểm chứng trả lời câu hỏi khác: *“Với dữ liệu, môi trường và yêu cầu cụ thể, chương trình có làm đúng điều cần làm không?”*. Để tin cậy một ứng dụng Java, cần cả hai loại bằng chứng này, cùng cách nhận diện giới hạn của chúng.