# Quan hệ giữa lazy constant, final và tối ưu của JVM

`final` và lazy constant cùng hướng tới một giá trị ổn định, nhưng giải quyết hai vấn đề khác nhau. `final` quy định một biến hoặc trường chỉ được gán một lần. Lazy constant cho phép trì hoãn việc tạo giá trị đến lần truy cập đầu tiên, sau đó giữ nguyên giá trị đó. Khi các điều kiện phù hợp được đáp ứng, JVM có thể xem nội dung lazy constant như một hằng số để thực hiện các tối ưu tương tự tối ưu dành cho trường `final`.

Trong Java 26, lazy constant được giới thiệu qua JEP 526 dưới dạng **preview API lần thứ hai**. Cần tách bạch ba lớp: quy tắc của ngôn ngữ Java về `final`, cơ chế khởi tạo an toàn của `LazyConstant`, và tối ưu mà JIT có thể thực hiện khi chương trình chạy.

## 1. `final` không đồng nghĩa với hằng số biên dịch hay bất biến sâu

Một biến `final` chỉ được gán một lần. Sau khi được gán, biến giữ nguyên giá trị đó. Nếu biến giữ tham chiếu đến một đối tượng, tham chiếu không thể trỏ sang đối tượng khác, nhưng trạng thái bên trong đối tượng vẫn có thể thay đổi.

```java
static final int MAX_RETRIES = 3;
static final String REGION = "ap-southeast-1";

static final List<String> ALLOWED_REGIONS =
        new ArrayList<>(List.of("ap-southeast-1"));

// Hợp lệ: tham chiếu ALLOWED_REGIONS không đổi,
// nhưng nội dung danh sách vẫn có thể thay đổi.
static void addRegion(String region) {
    ALLOWED_REGIONS.add(region);
}
```

Java Language Specification còn định nghĩa khái niệm **constant variable**. Một biến chỉ thuộc loại này khi đồng thời:

- Được khai báo `final`.
- Có kiểu nguyên thủy hoặc `String`.
- Được khởi tạo bằng một constant expression.

Vì vậy, `MAX_RETRIES` và `REGION` là constant variable. Một trường như `static final Pattern EMAIL = Pattern.compile(...)` hoặc `static final Parser PARSER = new Parser()` không phải constant variable, dù có từ khóa `final`.

Sự phân biệt này quan trọng vì trình biên dịch Java có thể đưa giá trị của constant variable vào bytecode của lớp sử dụng nó. Nếu thư viện thay đổi giá trị hằng nhưng ứng dụng phụ thuộc không được biên dịch lại, ứng dụng có thể tiếp tục dùng giá trị cũ đã được nhúng trong bytecode. Trường `final` tham chiếu đến đối tượng được tạo lúc chạy không có cùng quy tắc nhúng hằng này.

## 2. Trường `final` thường được khởi tạo sớm

Trường `final` thông thường phải nhận giá trị trong quá trình tạo đối tượng hoặc khởi tạo lớp. Điều này phù hợp khi giá trị chắc chắn được dùng, nhưng có thể tạo chi phí không cần thiết nếu đối tượng đắt để tạo và một số luồng chạy không bao giờ dùng đến nó.

```java
public final class ParserProvider {
    // Parser được tạo khi ParserProvider được khởi tạo.
    private static final Parser PARSER = new Parser();

    public static Parser parser() {
        return PARSER;
    }
}
```

Với trường instance `final`, chi phí khởi tạo xảy ra mỗi lần tạo instance chứa trường đó. Với trường `static final`, chi phí xảy ra khi lớp được khởi tạo. Từ khóa `final` tự nó không trì hoãn hai thời điểm này.

Có thể tự viết cơ chế khởi tạo lười bằng trường có thể thay đổi và đồng bộ hóa, nhưng khi đó phải tự quản lý trạng thái chưa khởi tạo, truy cập đồng thời và việc công bố đối tượng. Trường có thể thay đổi cũng không cung cấp cho JVM cùng cam kết ổn định như một giá trị chỉ được thiết lập một lần.

## 3. Lazy constant kết hợp khởi tạo lười với giá trị chỉ thiết lập một lần

Java 26 cung cấp `java.lang.LazyConstant<T>`, một kiểu giữ một nội dung được tính từ `Supplier`. Việc tạo holder không chạy phép tính. Lần gọi `get()` đầu tiên mới chạy hàm tính và thiết lập nội dung; các lần gọi sau nhận lại nội dung đã được thiết lập.

```java
public final class ParserProvider {
    private static final LazyConstant<Parser> PARSER =
            LazyConstant.of(Parser::new);

    private ParserProvider() {
    }

    public static Parser parser() {
        return PARSER.get();
    }
}
```

`LazyConstant` nằm trong `java.lang`, nên không cần import riêng. Ví dụ giả định ứng dụng có lớp `Parser` với constructor không tham số.

Ở đây có hai lớp `final` và ổn định:

1. Trường `PARSER` là `static final`, nên tham chiếu đến holder không thể bị thay thế sau khi lớp khởi tạo.
2. Nội dung bên trong holder ban đầu chưa có. Sau khi `PARSER.get()` tính và thiết lập nội dung thành công, nội dung đó không thể được thay bằng giá trị khác.

Sự kết hợp này giải quyết khác biệt giữa **thời điểm tạo** và **tính ổn định sau khi tạo**. Ứng dụng có thể trì hoãn một parser đắt tiền, nhưng không phải tự viết một trường cache có thể thay đổi để lưu kết quả.

### An toàn khi nhiều luồng cùng truy cập

`LazyConstant` bảo đảm việc khởi tạo là nguyên tử và hàm tính được chọn chạy tối đa một lần cho một lần khởi tạo thành công. Nếu nhiều luồng cùng gọi `get()` khi nội dung chưa có, một luồng chạy hàm tính; các luồng còn lại chờ đến khi quá trình khởi tạo hoàn tất rồi nhận cùng nội dung.

Việc tính toán và khởi tạo nội dung có quan hệ *happens-before* với lần đọc nội dung đã khởi tạo. Vì vậy, đối tượng được tạo và các trường `final` của nó được công bố an toàn cho các luồng khác. Hàm tính chạy trên luồng gọi `get()`. Nếu hàm tính bị chặn vô thời hạn, các luồng đang chờ cùng holder cũng có thể phải chờ vô thời hạn; API không cung cấp timeout hay cơ chế hủy phép tính.

Không nên tạo đồ thị phụ thuộc vòng giữa các lazy constant. Nếu hàm tính của một holder gọi lại chính holder đó trực tiếp hoặc gián tiếp, việc khởi tạo đệ quy sẽ thất bại. Nội dung `null` cũng không hợp lệ; nếu nghiệp vụ cần biểu diễn giá trị có thể vắng mặt, hãy giữ một `Optional<T>` làm nội dung.

## 4. JVM tối ưu lazy constant như thế nào?

**Constant folding** là tối ưu thay một phép đọc hoặc biểu thức có giá trị đã biết bằng chính giá trị đó, qua đó có thể bỏ các lần đọc bộ nhớ không cần thiết. Cần phân biệt hai trường hợp:

- **Ở thời điểm biên dịch Java:** `javac` có thể nhúng constant variable vào bytecode theo quy tắc của ngôn ngữ.
- **Khi chương trình chạy:** JIT có thể phân tích đường chạy và thực hiện constant folding cho một số trường `final`, lazy constant và cấu trúc dữ liệu được hỗ trợ. Đây là tối ưu lúc chạy, không phải việc `javac` biến mọi trường `final` thành hằng số.

Nội dung lazy constant chỉ đủ điều kiện cho tối ưu constant folding khi JVM có thể lần theo một đường tham chiếu đáng tin cậy bắt đầu từ trường `static final` đến lazy constant. Đường này có thể là tham chiếu trực tiếp hoặc đi qua các trường đáng tin cậy như `static final`, trường của record, hay trường instance `final` trong hidden class. Do đó, việc đặt holder trong một trường `static final` như ví dụ trên có ý nghĩa đối với khả năng tối ưu.

Khi lazy constant đã được khởi tạo, JVM có thể dùng nội dung đã quan sát thay cho những lần đọc nội dung tiếp theo. Từ đó, JIT có thể kết hợp constant folding với các tối ưu khác. Tuy nhiên, đặc tả cho phép JVM thực hiện tối ưu này; nó không cam kết mọi JVM, mọi đường chạy hoặc mọi lần gọi đều được tối ưu. Không nên suy luận rằng chỉ cần thêm `LazyConstant` là ứng dụng chắc chắn nhanh hơn.

Một lazy constant cũng không làm cho đối tượng được giữ bên trong trở nên bất biến sâu. Holder không cho thay nội dung sau khi khởi tạo, nhưng nội dung có thể là một đối tượng mutable, chẳng hạn `ArrayList`. Nếu cần chia sẻ an toàn theo nghĩa bất biến, bản thân kiểu đối tượng được giữ vẫn phải có thiết kế bất biến hoặc kiểm soát việc thay đổi. Holder giữ tham chiếu mạnh đến nội dung trong suốt thời gian holder còn được giữ, nên không phù hợp với dữ liệu lớn cần giải phóng hoặc làm mới theo chu kỳ.

## 5. Chọn `final`, lazy constant hay một cơ chế cache khác?

| Nhu cầu | Cách phù hợp | Lý do |
|---|---|---|
| Giá trị nguyên thủy hoặc `String` cố định, biểu diễn được bằng constant expression | Constant variable (`static final`) | Có ngữ nghĩa hằng ở cấp ngôn ngữ và có thể được nhúng vào bytecode |
| Đối tượng luôn cần ngay khi tạo instance hoặc khởi tạo lớp | Trường `final` | Đơn giản, giá trị sẵn sàng tại thời điểm khởi tạo |
| Đối tượng dùng chung, tốn chi phí tạo và có thể không bao giờ được truy cập | `LazyConstant<T>` | Trì hoãn phép tính, thiết lập nội dung tối đa một lần và công bố an toàn giữa các luồng |
| Giá trị cần hết hạn, làm mới, thay thế hoặc giải phóng | Cache có chính sách vòng đời rõ ràng | Lazy constant không có thao tác đặt lại hay xóa nội dung |

Nếu cần một singleton khởi tạo lười bằng API ổn định và không muốn phụ thuộc preview, có thể dùng initialization-on-demand holder idiom:

```java
public final class ParserProvider {
    private ParserProvider() {
    }

    private static class Holder {
        static final Parser INSTANCE = new Parser();
    }

    public static Parser parser() {
        return Holder.INSTANCE;
    }
}
```

JVM chỉ khởi tạo lớp `Holder` khi `parser()` lần đầu tham chiếu đến `Holder.INSTANCE`. Cơ chế khởi tạo lớp của Java bảo đảm an toàn giữa các luồng. Đây vẫn là lựa chọn phù hợp khi dự án cần API ổn định; `LazyConstant` hữu ích khi muốn mô hình hóa trực tiếp một nội dung được thiết lập lười và tận dụng tối ưu dành cho lazy constant.

## 6. Phiên bản Java và trạng thái preview cần kiểm tra

Tại ngày 27/11/2026, cần đọc tài liệu theo đúng JDK đang triển khai:

- **JDK 26:** JEP 526 đưa Lazy Constants vào preview lần thứ hai. API của JDK 26 có `of()`, `get()`, `isInitialized()` và `orElse()`.
- **JDK 27:** JEP 531 đưa tính năng vào preview lần thứ ba và API vẫn là preview, chưa phải API ổn định. `of()` và `get()` tiếp tục được hỗ trợ, nhưng `isInitialized()` và `orElse()` đã bị loại bỏ. Ví dụ trong bài chỉ dùng phần API chung này.
- **Xử lý lỗi cũng thay đổi giữa hai preview:** trên JDK 26, nếu hàm tính ném ngoại lệ, ngoại lệ được chuyển cho bên gọi và holder vẫn chưa khởi tạo; lần `get()` tiếp theo có thể thử tính lại. Trên JDK 27, lỗi unchecked khiến holder chuyển sang trạng thái lỗi; các lần `get()` tiếp theo ném `NoSuchElementException` và không chạy lại hàm tính. Không dựa vào hành vi lỗi của một bản preview khi nâng cấp sang JDK khác.

Để thử nghiệm trên JDK 26, bật preview ở cả lúc biên dịch và lúc chạy:

```bash
# Dùng bộ JDK 26 để biên dịch và chạy
javac --release 26 --enable-preview -d out src/ParserProvider.java
java --enable-preview -cp out com.example.Main
```

Nếu chuyển sang JDK 27, dùng chính bộ JDK 27 và mức phát hành 27:

```bash
# Dùng bộ JDK 27 để biên dịch và chạy
javac --release 27 --enable-preview -d out src/ParserProvider.java
java --enable-preview -cp out com.example.Main
```

Lớp được biên dịch phụ thuộc preview của một bản Java cụ thể và không thể dùng như lớp preview tương thích xuyên phiên bản. Vì vậy, phải thống nhất JDK biên dịch và JDK chạy; khi đổi phiên bản, biên dịch lại và kiểm tra lại API. Với thư viện hoặc hệ thống production cần cam kết tương thích dài hạn, không nên để `LazyConstant` preview trở thành kiểu công khai trong hợp đồng API trước khi tính năng được chuẩn hóa. Có thể thử nghiệm sau một lớp bao bọc nội bộ, đo thời gian khởi động, độ trễ lần truy cập đầu và hiệu năng sau khởi tạo, rồi quyết định dựa trên số đo thực tế.

## 7. Những điểm cần nhớ

- `final` bảo vệ việc gán lại biến hoặc trường; nó không tự làm đối tượng được tham chiếu trở nên bất biến sâu.
- Constant variable là một tập con hẹp của biến `final`: chỉ kiểu nguyên thủy hoặc `String`, được khởi tạo bằng constant expression.
- Lazy constant tách thời điểm khởi tạo khỏi thời điểm khai báo holder; nội dung được tính ở lần `get()` đầu tiên và không thay đổi sau khi khởi tạo.
- Trường `static final` là điểm neo quan trọng để JVM xem lazy constant là giá trị ổn định và có thể constant-fold.
- Constant folding là khả năng tối ưu của JIT, không phải cam kết tăng tốc cho mọi chương trình.
- JDK 26 và JDK 27 đều đánh dấu Lazy Constants là preview. Kiểm tra đúng phiên bản JDK, chữ ký API và hành vi lỗi trước khi nâng cấp hoặc đưa vào production.

## Tài liệu tham khảo

- [JEP 526: Lazy Constants (Second Preview), JDK 26](https://openjdk.org/jeps/526)
- [Java SE 26 API: `LazyConstant`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html)
- [Java SE 26 Core Libraries: Lazy Constants](https://docs.oracle.com/en/java/javase/26/core/lazy-constants.html)
- [Java Language Specification, Java SE 26, mục 4.12.4 — final Variables](https://docs.oracle.com/en/java/javase/26/docs/specs/jls26.pdf)
- [JDK 27 Release Notes: Lazy Constants (Third Preview)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Java SE 27 API: `LazyConstant`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html)
- [JEP 531: Lazy Constants (Third Preview), JDK 27](https://openjdk.org/jeps/531)
