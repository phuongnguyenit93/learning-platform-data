# Chọn ngoại lệ, Optional hay kiểu kết quả có cấu trúc trong thiết kế API Java

## Mục tiêu và bối cảnh

Một API có hai phần hợp đồng: **giá trị thành công** và **ý nghĩa của các kết cục khác**. Với Java Core, những kết cục khác có thể là “không có kết quả nhưng vẫn bình thường”, “yêu cầu bị từ chối theo quy tắc nghiệp vụ”, “tham số vi phạm tiền điều kiện” hoặc “không thể thực hiện do lỗi I/O/hạ tầng”. Ba công cụ `exception`, `Optional<T>` và **kiểu kết quả có cấu trúc** diễn đạt các ý nghĩa khác nhau.

Sau bài này, bạn sẽ biết cách chọn kiểu trả về theo ngữ nghĩa, thiết kế hợp đồng không nhập nhằng, vận dụng `sealed interface` và `record` trong Java 17, phân biệt checked/unchecked exception, xử lý nguyên nhân lỗi và kiểm thử đầy đủ các nhánh.

## 1. Phân loại trước khi chọn công cụ

| Kết cục | Ví dụ | Biểu diễn nên cân nhắc |
| --- | --- | --- |
| Thành công chắc chắn có giá trị | Tính tổng hai số hợp lệ | Trả `T` trực tiếp |
| Thành công nhưng có thể vắng mặt, không cần biết “vì sao” | Tìm sản phẩm theo mã; không có sản phẩm tương ứng | `Optional<Product>` |
| Nhiều kết cục nghiệp vụ **dự kiến**, mỗi nhánh có thông tin khác nhau | Yêu cầu mua hàng: được chấp nhận, mã không tồn tại, số lượng sai, không đủ hàng | `QuoteResult`/`Result<T,E>` |
| Người gọi dùng sai API hoặc vi phạm invariant | Truyền mã `null`/trống khi hợp đồng cấm | `IllegalArgumentException`, `NullPointerException` hoặc ngoại lệ phù hợp |
| Thao tác không thể hoàn thành do lỗi kỹ thuật | Không đọc được file, truy vấn database lỗi | Exception phù hợp, giữ nguyên `cause` |

Bảng là định hướng, không phải luật tuyệt đối. Ví dụ **số lượng âm** có thể là `InvalidQuantity` khi tiếp nhận biểu mẫu và muốn hiển thị lỗi sửa được; trong một API nội bộ yêu cầu `quantity > 0` từ caller đã xác thực, đó có thể là `IllegalArgumentException`. Câu hỏi cốt lõi là: **người gọi có dự kiến tình huống này và phải xử lý nó như một giá trị bình thường hay không?**

Trước khi viết chữ ký, hãy hỏi:
1. Phương thức có hoàn thành thành công theo hợp đồng không?
2. Nếu hoàn thành, người gọi cần phân biệt “không có giá trị” hay nhiều trạng thái khác nhau?
3. Nếu không hoàn thành, đó là sai hợp đồng của caller, lỗi hạ tầng hay invariant bị phá vỡ?
4. Người gọi nên tiếp tục, hiện thông báo, sửa dữ liệu, thử lại hay dừng xử lý?

## 2. Khi nào dùng exception?

Exception diễn đạt **luồng xử lý thành công bị gián đoạn**. `throw` làm phương thức ngừng trả giá trị bình thường; JVM tìm `catch` phù hợp qua các khung gọi. Exception có kiểu, thông điệp, stack trace và có thể có nguyên nhân gốc (`cause`). Không nên ném exception liên tục như cơ chế rẽ nhánh cho những trạng thái nghiệp vụ xảy ra thường xuyên.

Các loại hay dùng:

- **`IllegalArgumentException`**: giá trị tham số không đáp ứng tiền điều kiện đã công bố. Với tham số tham chiếu bắt buộc khác `null`, `Objects.requireNonNull` ném `NullPointerException` và có thể cho thông điệp rõ ràng.
- **`IllegalStateException`**: đối tượng hoặc tiến trình không ở trạng thái cho phép thao tác.
- **`IOException`**: thao tác I/O bị thất bại; người gọi có thể có phương án khác hoặc báo lỗi phù hợp.
- **Exception miền riêng**: dùng khi một loại lỗi bất thường có ý nghĩa xử lý riêng; tránh tạo nhiều class chỉ để đổi thông điệp.

### Checked và unchecked exception

`Exception` và các lớp con là **checked**, trừ `RuntimeException` và các lớp con (unchecked). `Error` cũng là `Throwable` nhưng thông thường không phải đối tượng cần bắt trong logic nghiệp vụ. Compiler yêu cầu bắt hoặc khai báo `throws` đối với checked exception; unchecked không bắt buộc khai báo.

| Tiêu chí | Checked, ví dụ `IOException` | Unchecked, ví dụ `IllegalArgumentException` |
| --- | --- | --- |
| Khi biên dịch | Cần `catch` hoặc `throws` | Không bắt buộc |
| Công dụng điển hình | Thất bại bên ngoài mà API muốn caller cân nhắc rõ ràng | Sai tiền điều kiện, trạng thái bất hợp lệ, hoặc lỗi có chính sách lan truyền |
| Rủi ro | Caller bắt đại hoặc phải chuyển tiếp qua nhiều tầng | Hợp đồng thiếu tài liệu khiến caller bỏ sót nhánh lỗi |

Không có quy tắc “lỗi nặng thì checked, lỗi nhẹ thì unchecked”. Cần xem tầng gọi **có thể khắc phục được gì**, chuẩn của thư viện đang dùng và tương thích chữ ký công khai.

Ví dụ Java sử dụng checked exception:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ConfigReader {
    static String read(Path path) throws IOException {
        return Files.readString(path);
    }
}
~~~

Đây là **lớp minh họa**, chưa có phương thức `main`. Khi file không đọc được, `Files.readString` ném `IOException` phù hợp; khi đọc thành công, kết quả là chuỗi. Không thể xác định stdout vì đoạn mã không thực thi đọc một file cụ thể. Đừng đổi lỗi đọc file thành `Optional.empty()`: “không tìm thấy dữ liệu sau khi tra cứu thành công” khác với “không biết dữ liệu có tồn tại vì I/O thất bại”.

Nếu API quyết định bọc checked exception thành unchecked, hãy giữ nguyên nhân:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ConfigService {
    static String requireConfig(Path path) {
        try {
            return Files.readString(path);
        } catch (IOException e) {
            throw new UncheckedIOException("Cannot read config: " + path, e);
        }
    }
}
~~~

Đoạn này cũng là minh họa không có `main`. `UncheckedIOException` giữ `cause` nên tầng trên vẫn truy ra lỗi gốc. Chỉ bọc khi hợp đồng cần điều đó; không mặc định mọi checked exception đều phải chuyển thành unchecked.

**Cách bắt exception đúng:** bắt ở ranh giới có khả năng xử lý (đổi nguồn dữ liệu, thử lại có giới hạn, hiển thị lỗi, ánh xạ HTTP response), hoặc bổ sung ngữ cảnh rồi ném tiếp. Tránh `catch (Exception ignored)`, trả `null`/`false` sau khi nuốt lỗi, bắt `Throwable`/`Error` trong logic bình thường, và ghi log lặp lại ở mọi tầng.

## 3. Khi nào dùng Optional<T>?

`Optional<T>` trả lời đúng một câu hỏi: **sau khi thao tác hợp lệ đã thực hiện, có một giá trị T hay không?** Nó không chứa nguyên nhân lỗi, số lượng sai, mã lỗi hay ngăn phương thức phát sinh exception.

Ví dụ:

~~~java
import java.util.Map;
import java.util.Optional;

class Catalog {
    private static final Map<String, String> NAMES =
            Map.of("P01", "Notebook");

    static Optional<String> findName(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        return Optional.ofNullable(NAMES.get(sku));
    }
}
~~~

Lớp `Catalog` là mã minh họa không có `main`. `findName("P01")` có giá trị, `findName("P02")` là Optional rỗng. Đầu vào `null` hoặc trắng vi phạm hợp đồng và bị ném exception; hai tình huống này không bị nhầm thành “mã hợp lệ nhưng không tìm thấy”.

Các API hữu ích:

| Phương thức | Ý nghĩa |
| --- | --- |
| `Optional.of(x)` | Tạo Optional có giá trị; `x == null` gây `NullPointerException` |
| `Optional.ofNullable(x)` | Trả có giá trị khi `x != null`, ngược lại rỗng |
| `Optional.empty()` | Biểu diễn vắng mặt hợp lệ |
| `map(f)`, `flatMap(f)` | Chuyển đổi khi có giá trị; `flatMap` dành cho hàm đã trả Optional |
| `filter(p)` | Giữ giá trị khi thỏa điều kiện |
| `ifPresent(f)`, `ifPresentOrElse(f, emptyAction)` | Xử lý một hoặc cả hai nhánh |
| `orElse(defaultValue)` | Dùng giá trị dự phòng; biểu thức đối số được đánh giá ngay |
| `orElseGet(supplier)` | Chỉ tính giá trị dự phòng khi Optional rỗng |
| `orElseThrow(supplier)` | Chuyển vắng mặt thành exception tại chỗ caller yêu cầu có giá trị |
| `isPresent()`, `isEmpty()` | Kiểm tra hai trạng thái |

Ví dụ người gọi quyết định chính sách:

~~~java
String name = Catalog.findName("P02").orElse("Chưa có tên");

String requiredName = Catalog.findName("P02")
        .orElseThrow(() -> new IllegalStateException("Product P02 is required"));
~~~

Các biểu thức này giả định `Catalog` đã được định nghĩa phía trên. Biểu thức đầu chọn giá trị thay thế; biểu thức thứ hai ném exception vì **caller áp đặt yêu cầu bắt buộc có bản ghi**. Không nên gọi `Optional.get()` khi chưa chắc có giá trị vì Optional rỗng sẽ gây `NoSuchElementException` và thường ít thông tin ngữ cảnh.

Những sai lầm thường thấy:
- **Trả `null` thay cho đối tượng Optional:** nếu chữ ký là `Optional<T>` thì luôn trả một Optional thực sự.
- **Nuốt lỗi hạ tầng và trả `empty()`:** không thể phân biệt mất kết nối với bản ghi không tồn tại.
- **Dùng `Optional<List<T>>` khi chỉ muốn báo tập rỗng:** thường chỉ cần trả `List.of()` hoặc một danh sách rỗng. Dùng Optional khi *bản thân sự vắng mặt của danh sách* có nghĩa riêng.
- **Lạm dụng Optional ở tham số và field:** Optional đặc biệt hữu ích ở **kiểu trả về**. Tham số tùy chọn có thể biểu đạt bằng overload, builder hoặc kiểu yêu cầu phù hợp; cân nhắc yêu cầu framework/serialization khi dùng Optional như field.
- **Lồng Optional không cần thiết:** khi phép chuyển đổi đã trả Optional, dùng `flatMap`.
- **Tưởng Optional thay thế validation:** đầu vào sai hoặc lỗi bất thường vẫn cần hợp đồng riêng.

## 4. Khi nào dùng kiểu kết quả có cấu trúc?

Khi thao tác có **nhiều kết cục hợp lệ theo quy trình nghiệp vụ**, người gọi cần loại trạng thái và dữ liệu tương ứng. Ví dụ đánh giá yêu cầu mua hàng có thể cho:
- `Accepted`: đủ điều kiện, kèm mã và số lượng;
- `UnknownProduct`: mã đã nhập không tồn tại;
- `InvalidQuantity`: số lượng người dùng yêu cầu không hợp lệ;
- `OutOfStock`: số lượng mong muốn lớn hơn tồn kho, kèm số lượng yêu cầu và hiện có.

Trả `boolean`, `null`, `Optional.empty()` hoặc ném một `RuntimeException("out of stock")` cho tất cả các trường hợp sẽ làm người gọi thiếu thông tin để hiển thị, sửa dữ liệu hoặc thống kê.

Trong Java 17+, **`sealed interface` + `record`** đặc biệt phù hợp. `sealed` giới hạn các kiểu được phép triển khai, trong khi mỗi `record` chứa dữ liệu có kiểu cho một trạng thái. `record` sinh accessor, `equals`, `hashCode` và `toString`, nhưng không tự kiểm tra quy tắc nghiệp vụ trong dữ liệu; cần constructor khi invariant đòi hỏi điều đó.

Một phương án chung khác là `Result<T,E>` với hai nhánh `Success<T,E>` và `Failure<T,E>`, trong đó `E` nên là enum/record/hierarchy có cấu trúc. Nếu `E` chỉ là một chuỗi tự do, caller rất dễ phải phân tích nội dung thông điệp bằng cách so chữ hoặc `contains`, dẫn đến API mong manh khi đổi ngôn ngữ.

### 4.1. Ví dụ đầy đủ Java 17: kết hợp ba cơ chế

Lưu mã sau dưới tên **`ApiOutcomeDemo.java`**. Catalog đặt trong bộ nhớ để kết quả có thể lặp lại. `quote` chỉ **đánh giá yêu cầu**, không thực hiện đặt hàng và không trừ tồn kho.

~~~java
import java.util.Map;
import java.util.Optional;

public class ApiOutcomeDemo {
    record Product(String sku, int available) {}

    sealed interface QuoteResult
            permits Accepted, UnknownProduct, InvalidQuantity, OutOfStock {}

    record Accepted(String sku, int quantity) implements QuoteResult {}
    record UnknownProduct(String sku) implements QuoteResult {}
    record InvalidQuantity(int quantity) implements QuoteResult {}
    record OutOfStock(String sku, int requested, int available) implements QuoteResult {}

    private static final Map<String, Product> STOCK = Map.of(
            "P01", new Product("P01", 5)
    );

    static Optional<Product> findProduct(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        return Optional.ofNullable(STOCK.get(sku));
    }

    static QuoteResult quote(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            return new InvalidQuantity(quantity);
        }
        Product product = STOCK.get(sku);
        if (product == null) {
            return new UnknownProduct(sku);
        }
        if (quantity > product.available()) {
            return new OutOfStock(sku, quantity, product.available());
        }
        return new Accepted(sku, quantity);
    }

    static String describe(QuoteResult result) {
        if (result instanceof Accepted ok) {
            return "OK " + ok.sku() + " x" + ok.quantity();
        }
        if (result instanceof UnknownProduct missing) {
            return "NOT_FOUND " + missing.sku();
        }
        if (result instanceof InvalidQuantity invalid) {
            return "INVALID_QUANTITY " + invalid.quantity();
        }
        if (result instanceof OutOfStock stock) {
            return "OUT_OF_STOCK " + stock.available();
        }
        throw new IllegalStateException("Unknown QuoteResult: " + result);
    }

    public static void main(String[] args) {
        System.out.println(findProduct("P01").isPresent());
        System.out.println(findProduct("P02").isEmpty());
        System.out.println(describe(quote("P01", 2)));
        System.out.println(describe(quote("P01", 8)));
        System.out.println(describe(quote("P02", 1)));
        System.out.println(describe(quote("P01", 0)));
        try {
            quote("", 2);
        } catch (IllegalArgumentException e) {
            System.out.println("EXCEPTION " + e.getMessage());
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac --release 17 ApiOutcomeDemo.java
java ApiOutcomeDemo
~~~

Stdout chính xác:

~~~text
true
true
OK P01 x2
OUT_OF_STOCK 5
NOT_FOUND P02
INVALID_QUANTITY 0
EXCEPTION sku must not be blank
~~~

Ý nghĩa từng nhánh:
1. `findProduct("P01")` trả Optional có giá trị; `findProduct("P02")` trả rỗng. Tìm kiếm vẫn hoàn thành theo hợp đồng.
2. `quote("P01", 2)` trả `Accepted`; `quote("P01", 8)` trả `OutOfStock` với `requested=8`, `available=5`.
3. `quote("P02", 1)` trả `UnknownProduct`, một kết cục nghiệp vụ dự kiến, khác với một lỗi database không thể truy vấn.
4. `quote("P01", 0)` trả `InvalidQuantity` để caller có thể nhắc người dùng sửa số lượng.
5. `quote("", 2)` ném `IllegalArgumentException` vì chuỗi trắng vi phạm tiền điều kiện của API.
6. `STOCK` bất biến. Nếu viết một phương thức đặt hàng thực sự, cần transaction/cạnh tranh truy cập và nhất quán tồn kho; một kết quả `quote` không bảo đảm giữ được hàng.

**Thứ tự kiểm tra cũng là hợp đồng.** Ví dụ ưu tiên số lượng không hợp lệ trước tra cứu SKU; khi vừa sai số lượng vừa không có sản phẩm, kết quả là `InvalidQuantity`. Nếu API muốn thông báo nhiều lỗi cùng lúc, nên trả một kết quả validation chứa danh sách lỗi.

Java 17 hỗ trợ ổn định `instanceof` pattern matching như trong ví dụ, nhưng `switch` pattern matching trong Java 17 còn là preview, vì vậy không đưa vào ví dụ cần chạy bằng `javac --release 17` thông thường. Đối với caller ở ngôn ngữ/phiên bản hỗ trợ switch toàn diện trên sealed hierarchy, có thể tận dụng kiểm tra exhaustiveness; còn chuỗi `if/else` Java 17 trong ví dụ phải tự xử lý đầy đủ biến thể.

### 4.2. Nhiều lỗi xác thực trong một kết quả

Thay vì dừng ở lỗi đầu tiên của biểu mẫu, có thể trả một cấu trúc bao gồm mã trường và mã lỗi:

~~~java
import java.util.List;

record FieldError(String field, String code) {}

record ValidationFailure(List<FieldError> errors) {
    ValidationFailure {
        errors = List.copyOf(errors);
    }
}
~~~

Hai record ở đây chỉ là ví dụ khai báo kiểu, không có `main`. `List.copyOf` tạo bản sao không thể chỉnh sửa qua list trả về và từ chối phần tử `null`; nếu muốn danh sách bắt buộc không rỗng thì cần kiểm tra thêm. Mã lỗi như `REQUIRED`, `NOT_INTEGER` hoặc `OUT_OF_RANGE` ổn định hơn thông điệp tự do. UI có thể tự bản địa hóa thông báo từ mã lỗi.

## 5. Ba công cụ có thể dùng trong cùng một API

Không cần ép cả module theo duy nhất một hình thức:

~~~text
findProduct(validSku)        -> Optional<Product>
quote(validSku, quantity)    -> QuoteResult
readConfig(path)             -> String, throws IOException
findProduct(blankSku)        -> IllegalArgumentException
~~~

Bảng chữ ký trên là **sơ đồ ý nghĩa**, không phải cú pháp khai báo Java hoàn chỉnh. Chúng phản ánh bốn tình huống: tra cứu có thể vắng mặt, kết cục nghiệp vụ nhiều nhánh, lỗi I/O bất thường và vi phạm hợp đồng gọi.

Thậm chí một phương thức khai báo `Result<Order, DomainError>` vẫn có thể ném ngoại lệ I/O nếu tầng dưới thất bại ngoài các kết cục nghiệp vụ dự kiến. Khi thiết kế, cần làm rõ loại lỗi nào là `DomainError` và loại nào truyền ra dưới dạng exception. Đừng tùy tiện quy đổi mọi `Exception` thành `Failure` vì có thể che lỗi lập trình đang làm hỏng invariant.

## 6. Tầng nào nên chuyển đổi kết cục?

| Nguồn tình huống | Tầng Java cần hiểu | Ranh giới giao tiếp có thể làm gì |
| --- | --- | --- |
| Tra cứu hợp lệ, không có bản ghi | Repository/service trả Optional theo hợp đồng | REST có thể biến vắng mặt thành 404 khi resource bắt buộc tồn tại |
| Không đủ hàng theo nghiệp vụ | Service trả `OutOfStock` | REST có thể ánh xạ thành 409 Conflict theo hợp đồng ứng dụng |
| Người dùng nhập sai dữ liệu | Validation/service trả result chứa mã lỗi | UI hiển thị từng trường; REST thường cân nhắc 400 hoặc 422 |
| Không kết nối được database | Hạ tầng truyền exception đủ nguyên nhân | Ranh giới REST xử lý thành lỗi máy chủ thích hợp; không báo 404 |
| Caller truyền tham số bị cấm | Phương thức ném exception về sai tiền điều kiện | Sửa caller hoặc bổ sung validation tại điểm tiếp nhận dữ liệu |

Các mã HTTP trên chỉ là ví dụ **chuyển đổi ở adapter**. `Optional.empty()` tự nó không “có nghĩa là HTTP 404”; trong Java Core, đó chỉ là kết quả rỗng. Tầng REST quyết định status dựa trên hợp đồng endpoint. Không trả stack trace, connection string hoặc thông tin nhạy cảm ra bên ngoài. Có thể log có ngữ cảnh ở ranh giới xử lý và giữ cause để chẩn đoán; tránh ghi trùng cùng lỗi ở mọi tầng.

**Retry:** chỉ thử lại lỗi có khả năng tạm thời và khi thao tác an toàn để thử lại; không retry đơn hàng có tác dụng phụ một cách mù quáng. “Không đủ hàng” hoặc “số lượng nhập âm” thường là trạng thái yêu cầu người dùng thay đổi, không phải lý do để retry tự động.

## 7. Cây quyết định nhanh

~~~text
Thao tác hoàn thành theo hợp đồng?
|
+-- CÓ
|   +-- Luôn có T                     -> T
|   +-- Chỉ có/không có T             -> Optional<T>
|   +-- Nhiều kết cục nghiệp vụ      -> Kiểu result có cấu trúc
|
+-- KHÔNG
    +-- Caller vi phạm tiền điều kiện -> Exception phù hợp
    +-- Sự cố I/O, trạng thái hỏng    -> Exception phù hợp, giữ cause
~~~

Đây là sơ đồ thiết kế, không phải chương trình Java. Nếu tình huống “không tìm thấy” cần thêm dữ liệu lỗi cụ thể hoặc phân biệt với “không đủ quyền”, “hết hạn”, “chưa được kích hoạt”, result type có cấu trúc có thể rõ hơn Optional. Nếu chỉ cần “có hay không”, Optional đơn giản và đủ ý nghĩa.

## 8. Thiết kế sai và hướng sửa

### A. `null` được dùng cho mọi thất bại

~~~java
// Anti-pattern: null vừa có thể là không tìm thấy,
// vừa là input sai, vừa là lỗi truy vấn.
Product findProduct(String sku) { /* ... */ return null; }
~~~

Đây là mã minh họa không độc lập, vì chưa có định nghĩa `Product` và phần thân thật. Hướng sửa: khai báo `Optional<Product>` cho không tìm thấy hợp lệ; exception cho sai tiền điều kiện và lỗi không thể hoàn thành; hoặc kiểu result khi các nhánh dự kiến cần phân biệt. Chỉ thay `null` bằng `Optional.empty()` mà giữ cách đánh đồng cũ thì chưa sửa được lỗi thiết kế.

### B. Ném exception để xử lý mọi sự kiện nghiệp vụ

~~~java
// Anti-pattern nếu hết hàng là trạng thái thường xuyên mà UI phải xử lý:
if (requested > available) {
    throw new IllegalStateException("out of stock");
}
~~~

Đây là fragment, giả sử `requested` và `available` đã được khai báo. Khi caller cần số lượng còn và cách đề xuất sửa đơn hàng, `OutOfStock(requested, available)` truyền được thông tin ngay trong kiểu dữ liệu. Ngược lại, tồn kho âm ngoài invariant có thể đúng là tình trạng bất thường nên ném exception.

### C. Nuốt lỗi hạ tầng rồi trả Optional rỗng

~~~java
// Anti-pattern: caller tưởng rằng chắc chắn không có bản ghi.
try {
    return repository.findById(id);
} catch (RuntimeException ignored) {
    return Optional.empty();
}
~~~

Fragment giả sử `findById` trả Optional. Truy vấn thất bại có nghĩa là **chưa xác định được** bản ghi có tồn tại không. Không được biến thành bằng chứng “không tồn tại”.

### D. Trả mã lỗi qua một chuỗi tự do

~~~java
record WeakResult(boolean success, String message) {}
~~~

Khi caller phải làm `message.contains("stock")` để ra quyết định, chỉ một thay đổi câu chữ hoặc ngôn ngữ cũng phá logic. Thay bằng subtype/mã lỗi ổn định và trường dữ liệu có kiểu; thông điệp chỉ dành cho hiển thị và chẩn đoán.

### E. Lạm dụng `Optional.get()` hoặc `orElse`

`get()` sẽ ném `NoSuchElementException` nếu rỗng. `orElse(expensiveFallback())` gọi `expensiveFallback()` ngay cả khi Optional có giá trị do quy tắc đánh giá đối số Java; dùng `orElseGet(() -> expensiveFallback())` khi cần tạo dự phòng lười. `Optional.of(null)` gây NPE; dùng `ofNullable` khi đầu vào có thể `null`.

## 9. Thiết kế hợp đồng API công khai

Một chữ ký tốt cần đi kèm tài liệu:
- **Tiền điều kiện:** có cho phép `null`, chuỗi trắng, số âm không? Điều kiện nào là validation do người dùng sửa và điều kiện nào là sai từ caller?
- **Thành công:** có thể trả `null` không? Có khả năng vắng mặt hay nhiều biến thể? Các record có cho phép trường rỗng không?
- **Thất bại:** checked exception nào trong `throws`; unchecked exception quan trọng nào phải ghi rõ; I/O error và cause được giữ thế nào?
- **Tác dụng phụ:** phương thức chỉ kiểm tra hay thật sự ghi dữ liệu? Retry có an toàn không?
- **Tương thích:** việc thêm subtype kết quả hoặc chuyển `T` thành `Optional<T>` có yêu cầu caller thay đổi không?

Đổi `Product findById(String)` thành `Optional<Product> findById(String)` là **thay đổi chữ ký Java**, buộc caller cập nhật. Với thư viện đã phát hành, cân nhắc tạo một API mới có tên rõ ràng và lộ trình chuyển đổi. Thêm biến thể mới vào sealed result hierarchy cũng là thay đổi hợp đồng với caller vốn giả định tập trường hợp cũ. Đừng coi `Result<T,String>` là sự bảo đảm tương thích khi ý nghĩa các chuỗi có thể thay đổi tùy ý.

Khi cần kết quả được chuẩn hóa qua nhiều API, có thể dùng `Result<T,E>` với `E` là kiểu lỗi miền. Nhưng tránh trừu tượng hóa chỉ để thay hai giá trị “có/không” đơn giản bằng một khuôn cồng kềnh.

## 10. Ma trận kiểm thử theo hợp đồng

| Đầu vào/tình huống | Hành vi kỳ vọng | Khẳng định quan trọng |
| --- | --- | --- |
| `findProduct("P01")` | Optional có Product | Giá trị tồn tại và đúng SKU |
| `findProduct("P02")` | Optional rỗng | Không ném do không có bản ghi |
| `findProduct("")` | `IllegalArgumentException` | Input sai không biến thành `empty()` |
| `quote("P01", 2)` | `Accepted` | Đúng SKU và số lượng |
| `quote("P01", 8)` | `OutOfStock` | `requested=8`, `available=5` |
| `quote("P02", 1)` | `UnknownProduct` | Không nhầm với lỗi truy vấn |
| `quote("P01", 0)` | `InvalidQuantity` | Mã lỗi cho caller sửa nhập liệu |
| Đồng thời số lượng sai và SKU không tồn tại | `InvalidQuantity` trong ví dụ | Thứ tự validation ổn định |
| File bị từ chối đọc | `IOException` hoặc wrapper có cause | Không rơi vào nhánh “vắng mặt” |
| API bọc lỗi I/O | `UncheckedIOException` có cause gốc | Không làm mất ngữ cảnh chẩn đoán |

Ở chương trình minh họa, `STOCK` là Map bất biến nên không có lỗi I/O; muốn test lỗi hạ tầng cần cung cấp dependency giả lập thất bại. Kiểm thử cần xác nhận **loại kết quả và các trường bên trong**, không chỉ chuỗi `toString()` hoặc thông điệp.

## 11. Checklist quyết định cuối cùng

1. Nếu chỉ có **một giá trị hoặc vắng mặt bình thường**, dùng `Optional<T>`; không dùng nó để giấu lỗi.
2. Nếu có **nhiều kết cục nghiệp vụ dự kiến và cần xử lý khác nhau**, dùng result type có kiểu cụ thể, chẳng hạn sealed hierarchy.
3. Nếu xảy ra **vi phạm tiền điều kiện, invariant hoặc thất bại thực thi bất thường**, dùng exception phù hợp, tránh biến nó thành mã “thành công rỗng”.
4. Bảo đảm giá trị và lỗi có dữ liệu đủ để caller xử lý, không buộc caller phân tích câu chữ.
5. Ghi rõ nullability, thứ tự validation, mức độ recoverable, side effect và tính an toàn khi retry.
6. Khi chuyển exception, giữ cause; khi chuyển result thành HTTP/UI, ánh xạ ở ranh giới giao tiếp.
7. Test thành công, vắng mặt, mọi nhánh nghiệp vụ, input sai và lỗi phụ thuộc bên ngoài.

**Bài tập vận dụng:** Thiết kế `parseAge(String raw)` cho biểu mẫu có thể nhận chuỗi trống, chữ không phải số, số ngoài khoảng cho phép hoặc tuổi hợp lệ. Hãy lý giải lợi ích của `MissingAge`, `NotANumber`, `OutOfRange` và `ValidAge` so với `Optional<Integer>`. Sau đó thiết kế `findUserById(long id)` với id hợp lệ và kết quả “không tìm thấy” là bình thường: `Optional<User>` có thể là lựa chọn sáng sủa nhất. Cuối cùng giả lập lỗi I/O ở kho dữ liệu và chứng minh API không đánh đồng “truy vấn thất bại” với “không có user”.

Tiêu chí cốt lõi: **kiểu trả về và ngoại lệ phải biểu đạt đúng ý nghĩa thực tế của từng kết cục**, giúp người gọi đưa ra quyết định chính xác.