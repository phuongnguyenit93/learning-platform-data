# Thiết kế API kế thừa dễ sử dụng bằng kiểu trả về phù hợp

## 1. Vấn đề: lớp con trả đúng đối tượng nhưng người dùng vẫn phải ép kiểu

Giả sử một API có lớp cha `Document` với thao tác sao chép:

```java
class Document {
    public Document copy() {
        return new Document();
    }
}
```

Lớp con `Report` biết bản sao của nó luôn là một `Report`. Nếu vẫn khai báo:

```java
// Minh họa phần khai báo trong lớp Report:
// @Override
// public Document copy() { ... }
```

thì lời gọi qua biến kiểu `Report` vẫn có kiểu kết quả là `Document`. Người dùng muốn dùng các khả năng riêng của Report sẽ phải kiểm tra hoặc ép kiểu, dù phần triển khai thật đã trả Report.

Kiểu trả về đồng biến (covariant return type) cho phép phương thức ghi đè trả một kiểu tham chiếu cụ thể hơn:

```java
// Minh họa phần khai báo trong lớp Report:
// @Override
// public Report copy() { ... }
```

Mục tiêu thiết kế là diễn đạt cam kết mà lớp con thực sự bảo đảm. Mã bên gọi qua `Report` nhận được kiểu chính xác hơn, còn bên gọi qua `Document` vẫn dùng được hợp đồng tổng quát.

Đây là quy tắc hiện hành trong Java, không phải một kỹ thuật chỉ dùng cho mã Java 5 cũ. Ví dụ trong bài chạy trên Java 17+.

## 2. Nguyên tắc: lớp con làm mạnh hơn cam kết về kết quả

Nếu phương thức lớp cha trả `Document`, bên gọi có quyền kỳ vọng kết quả phù hợp với kiểu Document. Lớp con trả `Report`, mà Report là một Document, vẫn đáp ứng kỳ vọng về kiểu đó.

Cần phân biệt:

- Kiểu trả về hẹp hơn không cho phép đổi tùy ý hợp đồng nghiệp vụ.
- Trả Report không tự bảo đảm kết quả khác null, không chia sẻ dữ liệu hoặc đã được kiểm tra đầy đủ.
- Quy tắc áp dụng cho kiểu tham chiếu phù hợp; không thể đổi `int` thành `long` chỉ vì hai kiểu đều là số.
- Tham số vẫn phải đáp ứng quy tắc ghi đè. Đổi một tham số từ Document thành Report thường tạo nạp chồng, không phải ghi đè phương thức nhận Document.

Với các API học tập thông thường, nên dùng `@Override` để trình biên dịch kiểm tra ý định ghi đè.

## 3. Ví dụ đầy đủ: sao chép và chuỗi cấu hình

Lưu thành `CovariantApiDemo.java`:

```java
import java.util.Objects;

public class CovariantApiDemo {
    static class Document {
        private String title;

        Document(String title) {
            this.title = Objects.requireNonNull(title);
        }

        public String title() {
            return title;
        }

        public Document withTitle(String title) {
            this.title = Objects.requireNonNull(title);
            return this;
        }

        public Document copy() {
            return new Document(title);
        }
    }

    static final class Report extends Document {
        private String format;

        Report(String title, String format) {
            super(title);
            this.format = Objects.requireNonNull(format);
        }

        public String format() {
            return format;
        }

        public Report withFormat(String format) {
            this.format = Objects.requireNonNull(format);
            return this;
        }

        @Override
        public Report withTitle(String title) {
            super.withTitle(title);
            return this;
        }

        @Override
        public Report copy() {
            return new Report(title(), format);
        }
    }

    public static void main(String[] args) {
        Report report = new Report("Draft", "TEXT");
        Report returned =
                report.withTitle("Quarterly").withFormat("PDF");

        System.out.println("same receiver=" + (returned == report));
        System.out.println("report="
                + report.title() + "/" + report.format());

        Report snapshot = report.copy();
        System.out.println("copy distinct=" + (snapshot != report));
        snapshot.withTitle("Snapshot");

        System.out.println("original title=" + report.title());
        System.out.println("copy="
                + snapshot.title() + "/" + snapshot.format());

        Document baseView = report;
        Document result = baseView.copy();
        System.out.println("base result runtime="
                + result.getClass().getSimpleName());
        System.out.println("base result title=" + result.title());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 CovariantApiDemo.java
java CovariantApiDemo
```

Kết quả:

```text
same receiver=true
report=Quarterly/PDF
copy distinct=true
original title=Quarterly
copy=Snapshot/PDF
base result runtime=Report
base result title=Quarterly
```

Ví dụ có hai hợp đồng kết quả khác nhau:

- `withTitle` và `withFormat` sửa đối tượng hiện tại rồi trả `this`.
- `copy` tạo một đối tượng mới.

Kiểu trả về Report hỗ trợ cả hai cách, nhưng bản thân tính đồng biến không quyết định đối tượng có được sửa hay được sao chép. API phải công bố ý nghĩa đó.

## 4. Vì sao chuỗi gọi cần ghi đè phương thức cấu hình?

Nếu Report chỉ kế thừa `Document.withTitle` mà không ghi đè, biểu thức:

```java
report.withTitle("Quarterly")
```

có kiểu tĩnh là Document. Lời gọi nối tiếp `.withFormat("PDF")` không hợp lệ vì Document không khai báo phương thức đó.

Ghi đè:

```java
@Override
public Report withTitle(String title) {
    super.withTitle(title);
    return this;
}
```

giữ phần kiểm tra và cập nhật dùng chung trong lớp cha, đồng thời làm rõ rằng lời gọi qua Report trả lại một Report.

Cách này có giá trị khi:

- Số lớp con và số phương thức cấu hình còn nhỏ.
- Mỗi lớp con có thêm thao tác riêng cần nối chuỗi.
- Các phương thức thật sự có cùng ngữ nghĩa.
- Việc trả `this` là hợp đồng mong muốn.

Không nên thay kiểu trả về để che một khác biệt hành vi. Nếu `withTitle` ở lớp cha sửa đối tượng nhưng phiên bản lớp con âm thầm tạo bản sao, người dùng qua Document có thể bị bất ngờ dù quan hệ kiểu vẫn biên dịch.

Tên `with...` không tự có nghĩa bất biến trong Java. Trong ví dụ nó được tài liệu hóa là thao tác thay đổi đối tượng. Nếu dự án quy ước `with...` là tạo bản sao, hãy chọn tên khác hoặc thay toàn bộ hợp đồng cho nhất quán.

## 5. Kiểu tĩnh của biến nhận vẫn quyết định API nhìn thấy

Trong chương trình:

```java
Document baseView = report;
Document result = baseView.copy();
```

biến `baseView` có kiểu Document. Trình biên dịch kiểm tra lời gọi theo chữ ký `Document.copy()`, nên kiểu của biểu thức lời gọi là Document.

Lúc chạy, đối tượng là Report và cơ chế điều phối phương thức chọn `Report.copy()`. Đối tượng kết quả thực tế là Report, nhưng điều đó không làm kiểu tĩnh của `result` tự đổi.

Vì vậy:

```java
// Không biên dịch:
// Report precise = baseView.copy();

// Hợp lệ:
Report precise = report.copy();
```

Không nên thiết kế API đòi người dùng ép kiểu không kiểm tra chỉ để dùng một thao tác cơ bản. Nếu bên gọi có lý do làm việc qua kiểu cha, hãy bảo đảm kiểu cha đã cung cấp đủ hợp đồng cần thiết. Chỉ dùng khả năng riêng của lớp con ở nơi mã thực sự cần và biết kiểu cụ thể.

## 6. Chọn kiểu trả về nào cho từng mục đích?

| Mục đích | Kiểu trả về nên cân nhắc | Điều cần công bố |
| --- | --- | --- |
| Thao tác dùng chung qua đa hình | Interface hoặc lớp cha biểu đạt năng lực cần thiết | Bên gọi được bảo đảm thao tác gì |
| Lớp con luôn tạo một kết quả đúng kiểu con | Kiểu con ở phương thức ghi đè | Có tạo mới, sao chép sâu hay chia sẻ dữ liệu |
| Cấu hình nối chuỗi trên chính đối tượng | Kiểu lớp hiện tại nếu cam kết trả this | Tính thay đổi, null, an toàn luồng |
| Trả một tập hợp | Interface collection thích hợp | Khả năng sửa, thứ tự, quyền sở hữu dữ liệu và kiểu phần tử |

“Cụ thể hơn” không tự đồng nghĩa “thiết kế tốt hơn”. Nếu API chỉ cần cam kết trả `List<Item>`, trả một lớp triển khai đặc biệt có thể làm người dùng phụ thuộc vào chi tiết không muốn bảo đảm lâu dài.

Tại lớp con, chỉ thu hẹp kiểu trả về khi kết quả luôn đáp ứng cam kết đó. Không thể thu hẹp thành Report rồi đôi khi trả một Document khác loại.

## 7. Những giới hạn không nên bỏ qua

### 7.1. Generic không tự đồng biến theo phần tử

Dù Report là kiểu con của Document, `List<Report>` không phải kiểu con của `List<Document>`. Vì vậy không thể chỉ đổi:

```java
// Lớp cha:
// public java.util.List<Document> load() { ... }

// Lớp con không thể ghi đè bằng:
// public java.util.List<Report> load() { ... }
```

Nếu hợp đồng thực sự dành cho bên đọc, có thể cân nhắc để lớp cha trả `List<? extends Document>`; khi đó một lớp con có thể trả `List<Report>` theo quan hệ kiểu phù hợp. Tuy nhiên wildcard làm thay đổi các thao tác bên gọi có thể thực hiện, nên phải thiết kế dựa trên nhu cầu thực, không thêm chỉ để vượt lỗi biên dịch.

Không dùng raw type hoặc ép kiểu unchecked để giả vờ có quan hệ đồng biến mà hệ thống kiểu không bảo đảm.

### 7.2. Không đổi kiểu tham số thành kiểu con để “đồng biến toàn bộ”

Ví dụ:

```java
// Lớp cha: public Document merge(Document other)
// Lớp con: public Report merge(Report other)
```

Phiên bản nhận Report không ghi đè phiên bản nhận Document; nó là một khai báo nạp chồng. Muốn ghi đè, phương thức lớp con vẫn phải nhận Document và chỉ có thể thu hẹp kết quả phù hợp.

Nếu lớp con không thể xử lý toàn bộ đối số hợp lệ của hợp đồng lớp cha, cần xem lại quan hệ kế thừa. Chỉ đổi chữ ký cho biên dịch không giải quyết sự không tương thích đó.

### 7.3. Không áp dụng cho constructor hoặc điều phối static

Constructor không có kiểu trả về nên không dùng quy tắc này.

Phương thức static có cơ chế che phương thức, không tham gia ghi đè và điều phối động theo đối tượng như ví dụ. Không nên dùng một ví dụ static để giải thích lợi ích đa hình của kiểu trả về đồng biến.

Các giới hạn ghi đè khác như quyền truy cập và ngoại lệ checked vẫn giữ nguyên; thu hẹp kết quả không cho phép giảm quyền truy cập hoặc mở rộng tùy ý ngoại lệ checked.

## 8. Cẩn trọng khi mở rộng hệ phân cấp nhiều tầng

Nếu một lớp con khác tiếp tục mở rộng Report, phương thức trả Report không tự chuyển thành kiểu lớp cháu. Mỗi tầng có thể phải ghi đè các phương thức nối chuỗi nếu muốn giữ kiểu chính xác.

Trong ví dụ, Report được đánh dấu `final` để hợp đồng dễ kiểm soát: không có lớp cháu âm thầm kế thừa `copy()` rồi nhận một Report thay vì đúng kiểu lớp cháu.

Nếu API cần nhiều tầng builder mở rộng được, có thể cân nhắc thiết kế generic có tham số kiểu “chính nó” hoặc tách các builder bằng tổ hợp. Đó là quyết định thiết kế riêng, có độ phức tạp và ràng buộc; không nên triển khai bằng một phép ép `(T) this` chưa được chứng minh an toàn.

Với một hệ phân cấp nhỏ, ghi đè tường minh như ví dụ thường dễ hiểu hơn một khung generic phức tạp.

## 9. Hợp đồng kết quả quan trọng hơn việc loại bỏ một phép ép kiểu

Trước khi xuất bản API, cần trả lời:

1. Kết quả có thể null không?
2. Kết quả là chính đối tượng hiện tại hay một đối tượng mới?
3. Nếu sao chép, những thành phần có thể thay đổi có được sao chép hay vẫn chia sẻ?
4. Bên gọi có được sửa kết quả không?
5. Phương thức có giữ cùng ý nghĩa khi gọi qua kiểu cha không?
6. Có thực sự cần kế thừa, hay một interface nhỏ/tổ hợp biểu đạt quan hệ rõ hơn?

Ví dụ dùng String cho title và format, nên tạo Report mới với cùng các chuỗi không chia sẻ trạng thái chuỗi có thể sửa. Nếu thay chúng bằng danh sách hoặc một đối tượng cấu hình có thể thay đổi, phải quyết định riêng cách sao chép dữ liệu đó.

Kiểu trả về đồng biến chỉ đảm bảo quan hệ kiểu của kết quả. Nó không tự tạo sao chép sâu, tính bất biến hay khả năng thay thế về mọi hành vi.

## 10. Bài tập kiểm chứng

1. Bỏ phiên bản `Report.withTitle` rồi biên dịch lời gọi chuỗi trong chương trình. Giải thích lỗi qua kiểu tĩnh của kết quả trung gian.
2. Giữ `Report.copy`, đổi `Report report` thành một biến chỉ có kiểu Document ở vị trí gọi. Giải thích vì sao khả năng của Report không tự xuất hiện ở mức biên dịch.
3. Thêm `@Override` cho một phiên bản `merge(Report)` khi lớp cha chỉ có `merge(Document)`. Quan sát trình biên dịch phát hiện nhầm lẫn giữa ghi đè và nạp chồng.
4. Nếu yêu cầu copy không được chia sẻ một danh sách có thể thay đổi, bổ sung chính sách sao chép và kiểm tra độc lập với việc kiểu kết quả là Report.
5. Khi review một API, giải thích kiểu trả về hẹp hơn đang thêm cam kết nào cho bên gọi và phần triển khai có đáp ứng cam kết đó ở mọi nhánh hay không.

## Tài liệu đối chiếu

- [JLS §8.4.5 — Kiểu trả về và tính thay thế của kiểu trả về](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.5).
- [JLS §8.4.8.3 — Các yêu cầu khi ghi đè và che phương thức](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.3).
- [JLS §15.12 — Kiểm tra lời gọi và điều phối phương thức](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12).
