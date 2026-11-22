# Giá trị null và ngoại lệ khi khởi tạo hoặc đóng tài nguyên trong try-with-resources

try-with-resources tự động gọi close() cho tài nguyên khi luồng thực thi rời khỏi khối try, dù khối kết thúc bình thường hay do ngoại lệ. Kiểu của tài nguyên phải là kiểu con của AutoCloseable (có thể là lớp hoặc interface); Closeable cũng dùng được vì nó mở rộng AutoCloseable.

Chủ đề này tập trung vào ba tình huống dễ gây nhầm lẫn: tài nguyên có giá trị null, biểu thức khởi tạo tài nguyên ném ngoại lệ, và phương thức close() ném ngoại lệ. Các quy tắc xử lý dưới đây vẫn là quy tắc của Java hiện hành. Cú pháp dùng biến tài nguyên đã khai báo bên ngoài được hỗ trợ từ Java 9.

## 1. Cú pháp và điều kiện của tài nguyên

Có thể khai báo tài nguyên ngay trong phần đầu try:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    // Đọc dữ liệu từ input.
}
~~~

Từ Java 9, có thể dùng một biến đã được khai báo trước đó:

~~~java
InputStream input = Files.newInputStream(path);

try (input) {
    // Đọc dữ liệu từ input.
}
~~~

Biến có sẵn trong resource specification phải được gán trước khi vào try và phải là final hoặc effectively final, nghĩa là không bị gán lại sau lần khởi tạo. Kiểu của biến phải là kiểu con của AutoCloseable. Nếu biến bị gán lại sau đó, cách viết try (input) sẽ không biên dịch.

Có thể khai báo nhiều tài nguyên, phân tách bằng dấu chấm phẩy. Java khởi tạo chúng từ trái sang phải và đóng chúng theo thứ tự ngược lại. Vì vậy, nếu tài nguyên thứ hai phụ thuộc vào tài nguyên thứ nhất, hãy khai báo tài nguyên thứ nhất trước để nó được đóng sau.

## 2. Tài nguyên có giá trị null

Một tài nguyên có thể nhận giá trị null. Nếu giá trị của tài nguyên là null, try-with-resources bỏ qua lời gọi close() cho tài nguyên đó. Bản thân giá trị null không làm phát sinh NullPointerException khi khối try kết thúc.

Khối try vẫn được thực thi bình thường. Chỉ thao tác đóng tài nguyên null được bỏ qua.

~~~java
DemoResource optional = null;

try (optional) {
    System.out.println("Khối try vẫn chạy");
}
~~~

Quy tắc này cũng áp dụng khi biểu thức khởi tạo tài nguyên trả về null:

~~~java
try (DemoResource resource = findOptionalResource()) {
    useResourceIfPresent(resource);
}
~~~

Nếu findOptionalResource() trả về null, thân try vẫn chạy và close() không được gọi cho resource.

Cần phân biệt tài nguyên tùy chọn với tài nguyên bắt buộc. Nếu nghiệp vụ yêu cầu tài nguyên luôn tồn tại, hãy kiểm tra null rõ ràng thay vì dựa vào việc try-with-resources tự bỏ qua close():

~~~java
DemoResource required = Objects.requireNonNull(
    createRequiredResource(),
    "Tài nguyên bắt buộc không được null"
);

try (required) {
    useResource(required);
}
~~~

Ví dụ trên cần import java.util.Objects. Nếu createRequiredResource() trả về null, Objects.requireNonNull ném NullPointerException trước khi bắt đầu khối try.

## 3. Ngoại lệ khi khởi tạo tài nguyên

Các biểu thức khởi tạo được đánh giá lần lượt từ trái sang phải. Nếu một biểu thức khởi tạo ném ngoại lệ:

1. Thân khối try không được thực thi.
2. Các tài nguyên đã khởi tạo thành công trước đó vẫn được đóng theo thứ tự ngược lại.
3. Tài nguyên có biểu thức khởi tạo thất bại không được xem là đã khởi tạo, nên không có close() cho tài nguyên đó.
4. Các tài nguyên nằm sau vị trí thất bại chưa được khởi tạo và cũng không được đóng.
5. Nếu việc đóng một tài nguyên đã khởi tạo lại ném ngoại lệ, ngoại lệ đóng đó được thêm vào danh sách suppressed của ngoại lệ khởi tạo ban đầu.

Ví dụ: tài nguyên R1 được tạo thành công, nhưng việc tạo R2 thất bại. Java sẽ bỏ qua thân try, gọi close() của R1, rồi ném ngoại lệ khởi tạo R2. Nếu close() của R1 cũng thất bại, lỗi đóng R1 là suppressed exception của lỗi khởi tạo R2.

Catch đặt sau try-with-resources có thể bắt ngoại lệ phát sinh trong quá trình khởi tạo, trong thân try hoặc khi đóng tài nguyên.

## 4. Ngoại lệ khi đóng tài nguyên

Khi rời khỏi thân try, Java lần lượt gọi close() theo thứ tự ngược với thứ tự khởi tạo. Một ngoại lệ từ close() không ngăn Java tiếp tục đóng các tài nguyên còn lại.

Kết quả phụ thuộc vào việc đã có ngoại lệ chính trước khi đóng hay chưa:

- **Thân try kết thúc bình thường và close() thất bại:** ngoại lệ từ lần đóng đầu tiên thất bại trở thành ngoại lệ chính được ném ra. Các ngoại lệ phát sinh từ những lần đóng tiếp theo được thêm vào nó dưới dạng suppressed exceptions.
- **Thân try đã ném ngoại lệ:** ngoại lệ của thân try vẫn là ngoại lệ chính. Mọi ngoại lệ phát sinh khi đóng tài nguyên được thêm vào ngoại lệ chính dưới dạng suppressed exceptions.
- **Khởi tạo tài nguyên đã thất bại:** ngoại lệ khởi tạo vẫn là ngoại lệ chính; ngoại lệ từ việc đóng các tài nguyên đã khởi tạo trước đó được thêm vào danh sách suppressed.

Có thể lấy các ngoại lệ bị suppressed bằng Throwable.getSuppressed(). Không nên chỉ ghi log ngoại lệ chính rồi bỏ qua danh sách này, vì lỗi đóng tài nguyên có thể chứa thông tin quan trọng về việc giải phóng file, socket, kết nối hoặc tài nguyên hệ thống.

Các khối catch và finally của một câu lệnh try-with-resources được thực thi sau khi Java đã thử đóng các tài nguyên. Vì vậy, catch có thể nhận ngoại lệ chính sau quá trình đóng; finally chạy sau các khối catch tương ứng.

## 5. Bảng tổng hợp hành vi

| Tình huống | Thân try | Tài nguyên được đóng | Ngoại lệ chính |
|---|---|---|---|
| Một tài nguyên có giá trị null | Vẫn chạy | Tài nguyên null được bỏ qua; các tài nguyên khác vẫn được đóng | Không có lỗi chỉ vì giá trị null |
| Biểu thức khởi tạo tài nguyên thứ N thất bại | Không chạy | Chỉ các tài nguyên đã khởi tạo trước N, theo thứ tự ngược | Ngoại lệ khởi tạo; lỗi đóng là suppressed |
| Thân try ném ngoại lệ | Đã chạy đến điểm ném | Tất cả tài nguyên đã khởi tạo và khác null, theo thứ tự ngược | Ngoại lệ từ thân try; lỗi đóng là suppressed |
| Thân try bình thường, close() thất bại | Chạy bình thường | Java vẫn thử đóng các tài nguyên còn lại | Lỗi đóng đầu tiên; lỗi đóng sau là suppressed |
| Mọi thao tác đều thành công | Chạy bình thường | Tất cả tài nguyên khác null, theo thứ tự ngược | Không có ngoại lệ |

## 6. Ví dụ Java chạy được

Ví dụ sau minh họa bốn trường hợp: tài nguyên null, lỗi khởi tạo, lỗi đóng khi thân try không lỗi, và lỗi đồng thời ở thân try cùng các thao tác đóng.

~~~java
public class TryWithResourcesNullAndExceptions {
    static final class DemoResource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        DemoResource(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
        }

        @Override
        public void close() throws Exception {
            System.out.println("close " + name);
            if (failOnClose) {
                throw new Exception("close " + name);
            }
        }
    }

    private static DemoResource createFailingResource() {
        System.out.println("initialize R2");
        throw new IllegalStateException("init R2");
    }

    public static void main(String[] args) throws Exception {
        nullResource();
        initializationFailure();
        closeFailuresWithoutPrimary();
        bodyAndCloseFailures();
    }

    private static void nullResource() throws Exception {
        System.out.println("-- null resource --");
        DemoResource optional = null;
        try (optional) {
            System.out.println("body");
        }
    }

    private static void initializationFailure() {
        System.out.println("-- initialization failure --");
        DemoResource first = new DemoResource("R1", true);
        try (first; DemoResource second = createFailingResource()) {
            System.out.println("body");
        } catch (Exception ex) {
            printException(ex);
        }
    }

    private static void closeFailuresWithoutPrimary() {
        System.out.println("-- close failures without body failure --");
        try (DemoResource first = new DemoResource("R1", true);
             DemoResource second = new DemoResource("R2", true)) {
            System.out.println("body");
        } catch (Exception ex) {
            printException(ex);
        }
    }

    private static void bodyAndCloseFailures() {
        System.out.println("-- body and close failures --");
        try (DemoResource first = new DemoResource("R1", true);
             DemoResource second = new DemoResource("R2", true)) {
            System.out.println("body");
            throw new IllegalStateException("body failure");
        } catch (Exception ex) {
            printException(ex);
        }
    }

    private static void printException(Exception ex) {
        System.out.println("primary: " + ex.getMessage());
        for (Throwable suppressed : ex.getSuppressed()) {
            System.out.println("suppressed: " + suppressed.getMessage());
        }
    }
}
~~~

Lưu nội dung trên trong tệp TryWithResourcesNullAndExceptions.java. Có thể biên dịch theo mức tương thích Java 17 và chạy bằng các lệnh:

~~~shell
javac --release 17 -encoding UTF-8 TryWithResourcesNullAndExceptions.java
java TryWithResourcesNullAndExceptions
~~~

Kết quả stdout chính xác:

~~~text
-- null resource --
body
-- initialization failure --
initialize R2
close R1
primary: init R2
suppressed: close R1
-- close failures without body failure --
body
close R2
close R1
primary: close R2
suppressed: close R1
-- body and close failures --
body
close R2
close R1
primary: body failure
suppressed: close R2
suppressed: close R1
~~~

Giải thích kết quả:

- **null resource:** thân try in ra body. Không có dòng close vì optional là null.
- **initialization failure:** R2 ném lỗi ngay trong lúc khởi tạo. Thân try không chạy. R1 được đóng; lỗi close R1 được suppressed lên lỗi init R2.
- **close failures without body failure:** thân try chạy xong. R2 được đóng trước R1. Lỗi close R2 là lỗi chính; lỗi close R1 được suppressed.
- **body and close failures:** lỗi body failure là lỗi chính. Java vẫn đóng R2 rồi R1; cả hai lỗi đóng đều được suppressed theo thứ tự phát sinh.

Trong ví dụ, biến first được khai báo trước và không bị gán lại, nên là effectively final và có thể xuất hiện trực tiếp trong resource specification theo cú pháp Java 9 trở lên. Biến second được khai báo ngay trong resource specification.

## 7. Cách xử lý trong mã ứng dụng

### Bảo toàn ngoại lệ chính và ngoại lệ suppressed

Khi cần xử lý hoặc ghi log, hãy kiểm tra cả ngoại lệ chính và các ngoại lệ suppressed. Đoạn sau là khung minh họa; Resource, openResource(), process() và logger được định nghĩa trong ứng dụng:

~~~java
try (Resource resource = openResource()) {
    process(resource);
} catch (IOException ex) {
    logger.error("Không thể xử lý tài nguyên", ex);

    for (Throwable closeError : ex.getSuppressed()) {
        logger.error("Lỗi bổ sung khi đóng tài nguyên", closeError);
    }

    throw ex;
}
~~~

Ví dụ này giả định openResource() và process() có thể ném IOException. Trong ứng dụng thực tế, hãy bắt kiểu ngoại lệ phù hợp với API đang dùng. Nếu cần bọc ngoại lệ để truyền qua một tầng khác, hãy giữ ngoại lệ ban đầu làm cause để không làm mất thông tin chẩn đoán.

### Thiết kế phương thức close()

Khi tự triển khai AutoCloseable:

- Giải phóng tài nguyên nền và cập nhật trạng thái đã đóng trước khi ném ngoại lệ báo lỗi đóng, nếu có thể.
- Khai báo kiểu ngoại lệ cụ thể mà thao tác đóng thực sự có thể ném; nếu đóng không thể thất bại thì không cần khai báo ngoại lệ.
- Tránh để close() ném InterruptedException. Khi ngoại lệ này bị suppressed, trạng thái interrupt của luồng có thể bị xử lý sai.
- Nên thiết kế close() có tính idempotent nếu phù hợp. AutoCloseable không bắt buộc close() phải idempotent, nên không được mặc định rằng gọi close() nhiều lần luôn an toàn. Riêng Closeable quy định rằng gọi close() sau khi luồng đã đóng không có tác dụng.

### Tránh đóng thủ công trùng với try-with-resources

Không gọi close() thủ công cho tài nguyên đang được quản lý bởi cùng một try-with-resources, trừ khi thiết kế vòng đời tài nguyên yêu cầu rõ ràng và việc đóng lặp lại đã được xử lý an toàn. Khi khối try kết thúc, Java vẫn gọi close(). Nếu close() không idempotent, việc đóng hai lần có thể gây lỗi hoặc tác dụng phụ.

Nếu cần kết thúc vòng đời tài nguyên sớm, hãy cân nhắc thu hẹp phạm vi của khối try để thời điểm tự động đóng đúng với nhu cầu.

### Chọn thứ tự khai báo khi tài nguyên phụ thuộc nhau

Giả sử Writer cần một OutputStream để hoạt động. Hãy khai báo OutputStream trước rồi mới khai báo Writer. Khi thoát khỏi try, Writer được đóng trước, sau đó OutputStream mới được đóng. Cách sắp xếp này giúp tài nguyên phụ thuộc được đóng trước tài nguyên mà nó sử dụng.

### Phân biệt tài nguyên tùy chọn và bắt buộc

Nếu null biểu thị “không có tài nguyên” hợp lệ, có thể dùng trực tiếp try-with-resources và để Java bỏ qua close(). Nếu null là trạng thái sai theo nghiệp vụ, hãy kiểm tra ngay tại ranh giới tạo hoặc nhận tài nguyên, ví dụ bằng Objects.requireNonNull. Việc kiểm tra sớm giúp lỗi xuất hiện tại đúng vị trí và tránh xử lý một trạng thái không hợp lệ trong thân try.

## 8. Những lỗi hiểu nhầm thường gặp

- **Cho rằng tài nguyên null sẽ luôn gây NullPointerException khi đóng:** sai; Java bỏ qua close() cho tài nguyên null.
- **Cho rằng lỗi khởi tạo làm rò rỉ các tài nguyên đã mở trước đó:** sai; các tài nguyên đã khởi tạo thành công vẫn được đóng theo thứ tự ngược.
- **Cho rằng một close() ném ngoại lệ sẽ ngăn các tài nguyên khác được đóng:** sai; Java tiếp tục thử đóng các tài nguyên còn lại.
- **Cho rằng lỗi close() luôn thay thế lỗi trong thân try:** sai; lỗi thân try hoặc lỗi khởi tạo đã xảy ra trước vẫn là ngoại lệ chính, còn lỗi đóng được suppressed.
- **Chỉ đọc getCause() để tìm lỗi đóng:** không đúng; lỗi đóng được truy xuất bằng getSuppressed().
- **Cho rằng biến tài nguyên có sẵn có thể bị gán lại:** sai; từ Java 9, biến dùng trực tiếp trong resource specification phải là final hoặc effectively final và đã được gán trước khi vào try.
- **Tự gọi close() rồi để try-with-resources tự đóng lần nữa:** có thể gây đóng lặp và tác dụng phụ nếu close() không idempotent.

## 9. Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 26 — mục 14.20.3, try-with-resources](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20.3): quy tắc khởi tạo, đóng tài nguyên, xử lý null và suppressed exceptions.
- [AutoCloseable — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng của close(), ngoại lệ, khuyến nghị triển khai và tính idempotent.
- [Java Language Changes by Release — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html): lịch sử cú pháp Java 9 cho biến final hoặc effectively final đã được khai báo trước.
- [Dev.java — Catching and Handling Exceptions](https://dev.java/learn/exceptions/catching-handling/): ví dụ về thứ tự đóng tài nguyên và cách đọc suppressed exceptions.