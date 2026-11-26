# Đối chiếu ý nghĩa ExampleMatcher với hành vi của store

Một `ExampleMatcher` có thể mô tả rất rõ yêu cầu “tên chứa An, bỏ qua hoa/thường”. Tuy nhiên, kết quả tìm kiếm còn phụ thuộc module Spring Data, ánh xạ của kiểu miền, phép so sánh của kho dữ liệu và dữ liệu thực tế. Cùng một cấu hình Java không phải là cam kết rằng mọi store sẽ tạo cùng truy vấn hoặc trả về cùng kết quả trong mọi môi trường.

Trong chương **Query by Example** của **SPRING_DATA_COMMONS**, bài học này hướng dẫn đối chiếu hai lớp: **ý nghĩa mà matcher diễn đạt** và **hành vi mà store thực thi**. Cách đối chiếu này giúp áp dụng các abstraction dùng chung của Spring Data đúng khả năng của từng loại kho dữ liệu, thay vì suy ra tính tương thích chỉ từ việc mã Java biên dịch thành công.

Sau bài học, bạn có thể:

- Phân biệt hợp đồng của API Commons với khả năng của module Spring Data cụ thể.
- Giải thích khác biệt do collation, giá trị null, trường không tồn tại và ánh xạ dữ liệu.
- Xác định bằng chứng cần thu thập khi kết quả QBE khác dự kiến.
- Thiết kế kiểm thử tích hợp xác nhận hành vi tìm kiếm trên store đang dùng.
- Quyết định khi nào tiếp tục dùng QBE và khi nào cần một cơ chế truy vấn khác.

## 1. Một truy vấn QBE đi qua những lớp nào?

Luồng xử lý có thể hình dung như sau:

~~~text
Yêu cầu nghiệp vụ
      |
      v
Probe + ExampleMatcher
      |
      v
Example<T>
      |
      v
Repository và module Spring Data của store
      |
      v
Truy vấn theo ánh xạ của kiểu miền
      |
      v
Store: dữ liệu, collation, chỉ mục, quy tắc null...
      |
      v
Kết quả được ánh xạ về đối tượng
~~~

Mỗi lớp trả lời một câu hỏi khác nhau:

| Lớp | Câu hỏi cần trả lời |
|---|---|
| Nghiệp vụ | Người dùng muốn “tìm giống” theo nghĩa nào? |
| Probe | Những thuộc tính nào thực sự đang có giá trị mẫu? |
| Matcher | Bỏ qua thuộc tính nào, kết hợp điều kiện ra sao, khớp chuỗi thế nào? |
| Module Spring Data | Có hỗ trợ cấu hình đó không và chuyển nó thành truy vấn bằng cách nào? |
| Ánh xạ | Đường dẫn Java tương ứng với cột, trường hoặc cấu trúc lưu trữ nào? |
| Store | Phép so sánh, null, collation và chỉ mục hoạt động ra sao? |
| Đọc kết quả | Dữ liệu nào được trả về và chuyển thành đối tượng thế nào? |

Không thể chỉ nhìn matcher để kết luận mọi hành vi phía dưới.

Ví dụ:

~~~java
Customer probe = new Customer();
probe.setDisplayName("An");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "displayName",
        ExampleMatcher.GenericPropertyMatchers
            .contains().ignoreCase()
    );

Example<Customer> example = Example.of(probe, matcher);
~~~

Ý định là: xét thuộc tính `displayName`, tìm chuỗi chứa `"An"` và bỏ qua khác biệt hoa/thường. Matcher không trực tiếp chỉ định SQL, cú pháp truy vấn MongoDB, tên chỉ mục hay collation cụ thể.

## 2. Commons cung cấp ngôn ngữ mô tả, module store cung cấp cách thực hiện

`Example`, `ExampleMatcher` và `QueryByExampleExecutor` thuộc phần abstraction dùng chung. Chúng giúp ứng dụng mô tả probe và tiêu chí mà không cần tự viết toàn bộ câu truy vấn.

Tuy nhiên, hỗ trợ QBE không chỉ là vấn đề có interface:

- Base repository phải cung cấp cách thực thi QBE phù hợp.
- Kiểu miền phải được store ánh xạ hợp lệ.
- Những lựa chọn matcher được sử dụng phải nằm trong khả năng của module.
- Dữ liệu và cấu hình store phải đáp ứng chính sách so sánh mà ứng dụng cần.

Ví dụ khai báo repository trong hai ứng dụng khác nhau:

~~~java
// Ứng dụng dùng Spring Data JPA
public interface CustomerJpaRepository
        extends JpaRepository<CustomerEntity, Long> {
}
~~~

~~~java
// Ứng dụng dùng Spring Data MongoDB
public interface CustomerMongoRepository
        extends MongoRepository<CustomerDocument, String> {
}
~~~

Hai kiểu miền có thể đại diện cùng khái niệm khách hàng nhưng khác cách ánh xạ và kiểu định danh. Không cần ép chúng thành một lớp chỉ để giữ mã QBE trông giống nhau.

Điểm có thể dùng chung là chính sách tìm kiếm, chẳng hạn “tên theo tiền tố, email theo toàn bộ giá trị”. Việc chuyển chính sách đó thành một `Example` và repository phù hợp vẫn phải tôn trọng mô hình của mỗi ứng dụng.

### 2.1. Biên dịch thành công chưa chứng minh store hỗ trợ

`ExampleMatcher.StringMatcher` có lựa chọn `REGEX`. Điều đó không có nghĩa mọi adapter đều thực hiện regex trong QBE.

Ví dụ:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withStringMatcher(ExampleMatcher.StringMatcher.REGEX);
~~~

Cấu hình Java trên có thể tạo được matcher. Nhưng khi thực thi:

- QBE của Spring Data JPA không hỗ trợ `REGEX`.
- Spring Data MongoDB có hỗ trợ khớp regex trong QBE.
- Với module khác, phải kiểm tra tập khả năng của chính module đó.

Không dựa vào giả định rằng lựa chọn không được hỗ trợ sẽ tự động chuyển thành `contains()` hoặc bị bỏ qua an toàn.

## 3. Lập bảng đối chiếu trước khi kết luận có lỗi

Một bảng đối chiếu hữu ích cần tách **ý định**, **cách triển khai** và **kết quả quan sát**.

| Cấu hình hoặc dữ liệu | Ý định ở mức QBE | Điểm cần đối chiếu với store |
|---|---|---|
| `exact()` | Khớp toàn bộ giá trị chuỗi | Phép bằng có phân biệt hoa/thường, dấu, khoảng trắng cuối hay không? |
| `startsWith()` | Khớp đầu chuỗi | Module dịch thế nào và chỉ mục có phù hợp không? |
| `contains()` | Khớp chuỗi con | Có dùng LIKE, regex hoặc cơ chế khác; ký tự đặc biệt được xử lý ra sao? |
| `ignoreCase()` | Yêu cầu bỏ qua hoa/thường | Store thực hiện bằng hàm, regex, collation hay cơ chế nào? |
| `caseSensitive()` | Yêu cầu phân biệt hoa/thường | Phép so sánh thực tế có đáp ứng được yêu cầu đó không? |
| Bỏ qua null | Không dùng giá trị null làm bộ lọc | Probe có thật sự null hay đang có giá trị mặc định? |
| Bao gồm null | Dùng null trong ví dụ | Store phân biệt null với trường không tồn tại thế nào? |
| `address.city` | Cấu hình thuộc tính lồng nhau | Đường dẫn có được ánh xạ, có được QBE hỗ trợ và có giá trị probe không? |
| `matchingAll()` | Kết hợp điều kiện được chọn bằng AND | Những điều kiện nào thật sự được đưa vào truy vấn? |
| `matchingAny()` | Kết hợp điều kiện được chọn bằng OR | Có điều kiện quá rộng khiến kết quả vượt dự kiến không? |

Bảng này không thay thế tài liệu của module. Nó giúp đặt đúng câu hỏi khi kiểm tra hành vi.

## 4. Khớp chuỗi: cùng ý định, cách dịch khác nhau

### 4.1. Ví dụ với tên khách hàng

Giả sử probe chứa:

~~~java
probe.setDisplayName("An");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "displayName",
        ExampleMatcher.GenericPropertyMatchers
            .startsWith().ignoreCase()
    );
~~~

Trong một store quan hệ, ý định có thể được diễn đạt bằng phép so sánh tương tự:

~~~sql
-- Minh họa ngữ nghĩa, không phải SQL được bảo đảm sinh ra.
WHERE LOWER(display_name) LIKE LOWER(:prefix)
-- :prefix mang ý nghĩa mẫu bắt đầu bằng "An"
~~~

Trong một store tài liệu, ý định có thể được diễn đạt bằng mẫu regex có neo đầu chuỗi và tùy chọn bỏ qua hoa/thường.

Hai cách có thể trả cùng kết quả với dữ liệu ASCII đơn giản, nhưng vẫn khác nhau ở:

- Quy tắc hoa/thường cho Unicode.
- Cách xử lý các ký tự đặc biệt.
- Khả năng dùng chỉ mục.
- Cách biểu diễn giá trị thiếu hoặc null.
- Chi phí thực thi với tập dữ liệu lớn.

Các ví dụ trên chỉ minh họa cách biểu đạt ý định. Muốn biết truy vấn chính xác, cần quan sát adapter và phiên bản đang chạy.

### 4.2. DEFAULT không phải chính sách nghiệp vụ đầy đủ

Nếu không đặt kiểu khớp cụ thể, matcher có thể sử dụng hành vi mặc định của store. Không nên diễn giải `StringMatcher.DEFAULT` thành “mọi store chắc chắn dùng cùng một phép so sánh”.

Nếu yêu cầu là tìm toàn bộ email, hãy mô tả rõ:

~~~java
.withMatcher(
    "email",
    ExampleMatcher.GenericPropertyMatchers.exact().ignoreCase()
)
~~~

Nếu yêu cầu là tìm tiền tố tên:

~~~java
.withMatcher(
    "displayName",
    ExampleMatcher.GenericPropertyMatchers.startsWith().ignoreCase()
)
~~~

Việc diễn đạt rõ không loại bỏ khác biệt của store, nhưng giảm sự mơ hồ khi đối chiếu.

### 4.3. Probe chứa dữ liệu, không chứa cú pháp truy vấn

Với `contains()`, hãy đặt probe là `"An"`, không tự biến thành `"%An%"`.

`"%"`, `"_"`, `"."` hay `"*"` có ý nghĩa khác nhau trong SQL LIKE và regex. Các module có thể xử lý ký tự đặc biệt để thực hiện kiểu khớp đã chọn. Không tự xem ký tự trong probe là toán tử truy vấn.

Nếu chủ động dùng `REGEX` ở một store hỗ trợ, chuỗi mẫu có thể mang cú pháp regex thật. Khi đó, chính sách cho phép mẫu và chi phí truy vấn phải được xác định riêng; nó không tương đương một ô tìm kiếm chuỗi con thông thường.

## 5. ignoreCase không bảo đảm mọi phép so sánh ngôn ngữ

### 5.1. Hoa/thường và collation

Xét dữ liệu:

~~~text
An
an
AN
~~~

`exact().ignoreCase()` diễn đạt ý định coi khác biệt hoa/thường là không quan trọng. Store có thể thực hiện yêu cầu qua biến đổi chữ, quy tắc so sánh hoặc mẫu truy vấn.

Ngược lại, `exact().caseSensitive()` không tự thay collation của cột hoặc cơ sở dữ liệu. Nếu adapter tạo phép bằng và phép bằng đó đang dùng collation không phân biệt hoa/thường, kết quả có thể vẫn coi `"An"` và `"an"` là bằng nhau.

Vì vậy, khi mã khách hàng bắt buộc phân biệt `"KH-001"` với `"kh-001"`, hợp đồng cần bao gồm cả cấu hình lưu trữ và phép so sánh thực tế. Chỉ nhìn lời gọi `caseSensitive()` là chưa đủ.

### 5.2. Không dấu và Unicode là các yêu cầu riêng

Những cặp sau kiểm tra các vấn đề khác nhau:

| Cặp giá trị | Vấn đề cần kiểm tra |
|---|---|
| `An` và `an` | Hoa/thường |
| `Da Nang` và `Đà Nẵng` | Dấu và cách so sánh ngôn ngữ |
| Một chữ có dấu được mã hóa theo hai dạng Unicode | Chuẩn hóa biểu diễn |
| `An` và `An ` | Khoảng trắng và quy tắc so sánh kiểu dữ liệu |

Không diễn giải `ignoreCase` thành chức năng bỏ dấu hoặc chuẩn hóa toàn bộ văn bản.

Nếu sản phẩm cần tìm không dấu, hãy thiết kế rõ cách lưu và truy vấn, chẳng hạn một trường tìm kiếm đã chuẩn hóa. Trường đó phải được duy trì nhất quán khi tạo, cập nhật và chuyển đổi dữ liệu cũ.

### 5.3. Lọc và sắp xếp là hai hợp đồng khác nhau

Tìm bằng `ignoreCase()` không tự tạo cách sắp xếp không phân biệt hoa/thường.

~~~java
repository.findAll(
    example,
    Sort.by("displayName").ascending()
);
~~~

Matcher xác định tập bản ghi được chọn. `Sort` mô tả thứ tự, còn store quyết định cách thực hiện so sánh thứ tự theo các khả năng và cấu hình của nó.

Hai store có thể chọn cùng một tập khách hàng nhưng sắp xếp khác nhau. Khi kiểm thử matcher, nên so tập định danh; khi kiểm thử thứ tự, cần một kiểm tra riêng với quy tắc sắp xếp rõ ràng.

## 6. Null trong probe và null trong store không cùng một câu hỏi

### 6.1. Bỏ qua null là quyết định khi xây điều kiện

~~~java
Customer probe = new Customer();
probe.setDisplayName("An");
// email = null

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreNullValues();
~~~

Ở đây, `email = null` có nghĩa không thêm bộ lọc email. Nó không có nghĩa truy vấn chỉ chọn bản ghi có email null.

Nếu mọi thuộc tính có ý nghĩa đều bị bỏ qua, probe có thể không còn điều kiện hữu hiệu. Khi đó truy vấn có thể chọn toàn bộ dữ liệu. Ứng dụng cần quy định có cho phép tìm không điều kiện hay phải yêu cầu ít nhất một tiêu chí.

### 6.2. Bao gồm null cần hiểu mô hình lưu trữ

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIncludeNullValues();
~~~

Khi chọn bao gồm null, cần rà soát tất cả thuộc tính của probe, không chỉ trường mà người dùng đang quan tâm. Các trường chưa được đặt giá trị cũng có thể tham gia điều kiện.

Trong cơ sở dữ liệu quan hệ, một cột có thể chứa SQL NULL. Trong kho tài liệu, có thể tồn tại hai trạng thái:

~~~json
{ "customerKey": "C01", "email": null }
~~~

~~~json
{ "customerKey": "C02" }
~~~

Tài liệu thứ nhất có trường `email` với giá trị null; tài liệu thứ hai không có trường đó.

Ở mức truy vấn MongoDB gốc, bộ lọc `{ "email": null }` có thể khớp cả hai trạng thái. Nhưng không vì thế mà kết luận mọi truy vấn QBE trên mọi store đều có đúng hành vi ấy. Cần xem module tạo bộ lọc gì và liệu matcher có đủ khả năng biểu đạt yêu cầu “có trường và giá trị là null” hay không.

Nếu nghiệp vụ cần phân biệt null với không tồn tại, truy vấn chuyên biệt của store có thể phù hợp hơn QBE.

### 6.3. Primitive và constructor làm thay đổi probe

~~~java
private boolean active;
~~~

Một đối tượng mới có `active = false` nếu không được đặt lại. Đây là một giá trị có thể tham gia điều kiện, dù giao diện chưa chọn trạng thái nào.

Trong khi đó:

~~~java
private Boolean active;
~~~

cho phép dùng `null` để biểu diễn không lọc, khi matcher bỏ qua null.

Cũng phải kiểm tra constructor, giá trị khởi tạo của trường và đối tượng con được tạo tự động. Nếu constructor đặt `active = true`, việc không gọi setter không khiến trường này trở về null.

Trước khi kết luận store diễn giải matcher sai, hãy quan sát probe thực tế mà repository nhận.

## 7. Ánh xạ và đường dẫn thuộc tính

### 7.1. Dùng tên thuộc tính Java

~~~java
.withMatcher(
    "displayName",
    ExampleMatcher.GenericPropertyMatchers.contains()
)
~~~

`displayName` là đường dẫn trong mô hình Java, dù tên lưu trữ có thể là `display_name` hoặc một tên khác do ánh xạ quy định.

Module Spring Data sử dụng metadata để chuyển đường dẫn sang cấu trúc của store. Không thay tên thuộc tính bằng tên cột chỉ vì đã nhìn thấy tên cột trong log SQL.

Tên đường dẫn dạng chuỗi cũng cần được xem lại khi đổi tên trường trong mô hình. Mã Java xung quanh vẫn có thể biên dịch trong khi cấu hình đường dẫn không còn hợp lệ.

### 7.2. Thuộc tính lồng nhau không bảo đảm truy vấn được mọi cấu trúc

~~~java
Address address = new Address();
address.setCity("Ha Noi");

Customer probe = new Customer();
probe.setAddress(address);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "address.city",
        ExampleMatcher.GenericPropertyMatchers
            .exact().ignoreCase()
    );
~~~

Cần kiểm tra:

1. `address.city` có phải đường dẫn hợp lệ của kiểu miền không?
2. Probe có giá trị thành phố thật không?
3. Store có hỗ trợ cách duyệt cấu trúc đó bằng QBE không?
4. Cách ánh xạ đối tượng nhúng hoặc quan hệ có tạo đúng điều kiện dự kiến không?

Một thuộc tính đơn lồng nhau không có cùng khả năng với collection hay map. Không suy từ ví dụ `address.city` rằng QBE sẽ diễn đạt được điều kiện “có ít nhất một phần tử orders thỏa cả hai điều kiện” trên mọi store.

### 7.3. Kiểu dữ liệu và converter cũng tham gia hành vi

Hai trường có cùng tên Java chưa chắc có cùng biểu diễn lưu trữ. Ví dụ, một trạng thái enum có thể được lưu thành chuỗi, số hoặc giá trị đã chuyển đổi.

Với kiểu ngày giờ, số hoặc kiểu giá trị tùy biến, cần kiểm tra cả ánh xạ và converter. QBE chủ yếu dùng so sánh bằng cho các giá trị không phải chuỗi; một giá trị mẫu không tự diễn đạt khoảng thời gian, lớn hơn hoặc nhỏ hơn.

Nếu yêu cầu là “tạo trong tháng này”, không đặt một ngày vào probe rồi kỳ vọng store suy ra cả khoảng ngày.

## 8. Cấu hình chung và cấu hình từng thuộc tính

Trước khi phân tích store, phải xác định matcher hiệu lực trên từng đường dẫn.

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING)
    .withIgnoreCase()
    .withMatcher(
        "email",
        ExampleMatcher.GenericPropertyMatchers.exact()
    )
    .withMatcher(
        "accountCode",
        ExampleMatcher.GenericPropertyMatchers
            .exact().caseSensitive()
    );
~~~

Ý nghĩa:

| Thuộc tính | Kiểu khớp | Hoa/thường |
|---|---|---|
| Chuỗi khác có giá trị trong probe | Chứa | Bỏ qua theo cấu hình chung |
| `email` | Toàn bộ giá trị | Kế thừa bỏ qua hoa/thường |
| `accountCode` | Toàn bộ giá trị | Yêu cầu phân biệt theo cấu hình riêng |

Một cấu hình riêng chỉ ghi đè những lựa chọn mà nó thiết lập. Không nên đọc `withMatcher("email", exact())` thành “xóa toàn bộ cấu hình chung cho email”.

Ngoài ra, `ExampleMatcher` là bất biến:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll();

// Kết quả matcher mới bị bỏ đi.
matcher.withIgnoreCase();
~~~

Cách đúng là giữ kết quả trả về:

~~~java
matcher = matcher.withIgnoreCase();
~~~

Những lỗi này nằm trước bước chuyển sang truy vấn store. Chúng không cần một lời giải thích bằng collation hay chỉ mục.

## 9. Một ví dụ hoàn chỉnh để đối chiếu

Giả định kiểu miền `Customer` có các thuộc tính `id`, `customerKey`, `displayName`, `email`, `accountCode`, `active` và getter/setter. `active` dùng `Boolean`; các bộ lọc chưa được chọn được để null.

~~~java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

public final class CustomerSearchExamples {

    private CustomerSearchExamples() {
    }

    public static Example<Customer> create(
            String name,
            String email,
            Boolean active) {

        Customer probe = new Customer();
        probe.setDisplayName(trimToNull(name));
        probe.setEmail(trimToNull(email));
        probe.setActive(active);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnoreNullValues()
            .withIgnorePaths("id", "customerKey", "accountCode")
            .withMatcher(
                "displayName",
                ExampleMatcher.GenericPropertyMatchers
                    .startsWith().ignoreCase()
            )
            .withMatcher(
                "email",
                ExampleMatcher.GenericPropertyMatchers
                    .exact().ignoreCase()
            );

        return Example.of(probe, matcher);
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }

        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
~~~

Ví dụ này quyết định rõ ba việc:

- Chuẩn hóa đầu vào trước khi tạo điều kiện.
- Chỉ dùng các thuộc tính được phép làm bộ lọc.
- Cấu hình kiểu khớp riêng cho tên và email.

Hàm `trimToNull` ở đây dùng `trim()`, không phải giải pháp chuẩn hóa toàn bộ khoảng trắng Unicode. Hãy thay đổi chính sách đó nếu miền dữ liệu cần.

Lời gọi:

~~~java
Example<Customer> example = CustomerSearchExamples.create(
    " an ",
    "AN@EXAMPLE.COM",
    Boolean.TRUE
);
~~~

được diễn giải ở mức nghiệp vụ là:

~~~text
displayName bắt đầu bằng "an", bỏ qua hoa/thường
AND email bằng "AN@EXAMPLE.COM", bỏ qua hoa/thường
AND active = true
~~~

Không có điều kiện theo `id`, `customerKey` hoặc `accountCode`.

Nếu kết quả sai, có thể lần lượt kiểm tra từng thành phần trên. Việc dùng một probe nhỏ giúp truy ra nguyên nhân dễ hơn so với dùng trực tiếp đối tượng nhận từ toàn bộ biểu mẫu.

## 10. Kiểm chứng hành vi trên store thực

### 10.1. Tách kiểm tra cấu hình và kiểm tra thực thi

Có hai câu hỏi khác nhau:

| Câu hỏi | Loại kiểm tra phù hợp |
|---|---|
| Hàm tạo Example có giữ đúng probe và matcher không? | Kiểm tra mã xây điều kiện |
| Store có thực hiện đúng yêu cầu tìm kiếm không? | Kiểm thử tích hợp với repository và store thật |

Một mock repository chỉ trả về danh sách đã định sẵn không chứng minh `ignoreCase()` hay `contains()` được store hỗ trợ đúng. Nó chỉ giúp kiểm tra sự tương tác hoặc logic xung quanh lời gọi.

Khi thay store hoặc thay phiên bản module, những kiểm tra đi qua adapter và kho dữ liệu mới cung cấp bằng chứng về hành vi truy vấn.

### 10.2. Bộ dữ liệu nhỏ nhưng phân biệt được các giả thuyết

Dùng một bộ dữ liệu có cả bản ghi phải khớp và phải bị loại:

| customerKey | displayName | email | active |
|---|---|---|---|
| `C01` | `An` | `An@Example.com` | `true` |
| `C02` | `an` | `an@other.com` | `false` |
| `C03` | `Binh An` | `binh.an@example.com` | `true` |
| `C04` | `Anh` | `anh@example.com` | `true` |
| `C05` | `Binh` | `binh@example.com` | `true` |

Giả sử store hỗ trợ các kiểu khớp đang xét và thực hiện bỏ qua hoa/thường theo cách thông thường với các chuỗi ASCII này:

| Probe và matcher | Tập khóa kỳ vọng |
|---|---|
| Tên `an`, `startsWith().ignoreCase()` | `C01, C02, C04` |
| Tên `an`, `contains().ignoreCase()` | `C01, C02, C03, C04` |
| Tên `an`, `exact().ignoreCase()` | `C01, C02` |
| Email `AN@EXAMPLE.COM`, `exact().ignoreCase()` | `C01` |
| Chỉ `active = false` | `C02` |
| Tên theo tiền tố `an` AND `active = true` | `C01, C04` |

Sự có mặt của `C03` giúp phân biệt tiền tố với chuỗi con. Sự có mặt của `C05` giúp phát hiện truy vấn vô tình không còn lọc theo tên.

### 10.3. Ví dụ kiểm tra kết quả không phụ thuộc thứ tự

Đoạn minh họa sau giả định `repository` thực thi `QueryByExampleExecutor<Customer>`, dữ liệu trên đã được nạp và bài kiểm thử có thư viện JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Example;

@Test
void findsActiveCustomersByNamePrefix() {
    Example<Customer> example = CustomerSearchExamples.create(
        "an",
        null,
        Boolean.TRUE
    );

    Iterable<Customer> rows = repository.findAll(example);

    Set<String> actualKeys = StreamSupport
        .stream(rows.spliterator(), false)
        .map(Customer::getCustomerKey)
        .collect(Collectors.toSet());

    Set<String> expectedKeys = new HashSet<>(
        Arrays.asList("C01", "C04")
    );

    assertEquals(expectedKeys, actualKeys);
}
~~~

Đây là phần thân minh họa trong một lớp kiểm thử tích hợp, không phải một cấu hình khởi động store hoàn chỉnh. Cách khởi tạo repository, ánh xạ kiểu miền và nạp dữ liệu phải theo module của ứng dụng.

So sánh tập khóa giúp kiểm tra điều kiện lọc mà không phụ thuộc thứ tự mặc định. Nếu ứng dụng cần kiểm tra cả thứ tự hoặc số lần xuất hiện của kết quả, hãy dùng một kiểm tra riêng phù hợp.

### 10.4. Thêm các trường hợp phụ thuộc môi trường

Ngoài bộ kiểm tra ASCII, nên có nhóm tình huống riêng:

- Hoa/thường trên mã tài khoản khi store dùng collation khác nhau.
- Thành phố có dấu và không dấu.
- Chuỗi rỗng, khoảng trắng và khoảng trắng cuối.
- Giá trị null so với trường không tồn tại trong kho tài liệu.
- Thuộc tính lồng nhau có giá trị và không có đối tượng cha.
- Ký tự đặc biệt trong chuỗi tìm kiếm.
- Kiểu matcher không được module hỗ trợ.

Không gán sẵn một kết quả “phải giống nhau ở mọi nơi” cho những tình huống mà hợp đồng store khác nhau. Trước hết phải quyết định ứng dụng muốn hành vi nào, rồi cấu hình hoặc chọn truy vấn để đạt hành vi ấy.

## 11. Thu thập bằng chứng khi kết quả khác dự kiến

Một quá trình điều tra hữu ích đi từ đầu vào tới kết quả:

1. **Cố định yêu cầu:** ghi lại tiêu chí nghiệp vụ và tập khóa kỳ vọng trên bộ dữ liệu nhỏ.
2. **Kiểm tra probe:** xác nhận giá trị sau chuẩn hóa, đặc biệt là null, chuỗi trắng và trường có giá trị mặc định.
3. **Kiểm tra matcher hiệu lực:** xem kiểu khớp, hoa/thường, đường dẫn bỏ qua và `matchingAll/Any`.
4. **Kiểm tra ánh xạ:** xác nhận tên thuộc tính, đối tượng nhúng, converter và kiểu dữ liệu lưu trữ.
5. **Quan sát truy vấn:** dùng khả năng logging hoặc công cụ theo dõi phù hợp với module.
6. **Đối chiếu store:** xem dữ liệu thô, collation và cách phép so sánh được thực hiện.
7. **Đánh giá chỉ mục:** sau khi đã hiểu kết quả đúng, kiểm tra kế hoạch thực thi và chi phí truy vấn.

Một bản ghi bằng chứng nên có:

| Thông tin | Mục đích |
|---|---|
| Phiên bản module Spring Data và store | Xác định môi trường thực thi |
| Probe sau chuẩn hóa | Biết chính xác giá trị đã truy vấn |
| Matcher hiệu lực | Biết quy tắc được yêu cầu |
| Ánh xạ liên quan | Hiểu đường dẫn và kiểu dữ liệu |
| Truy vấn và giá trị tham số | Kiểm tra cách adapter chuyển đổi |
| Dữ liệu mẫu | Tái hiện bản ghi khớp và không khớp |
| Kết quả thực tế và kỳ vọng | Xác định phần hợp đồng bị lệch |

Log truy vấn có thể không hiển thị giá trị tham số nếu chưa bật phần quan sát tương ứng. Đừng đọc một câu SQL có placeholder rồi suy ra giá trị bind mà chưa xác nhận.

Khi chia sẻ bằng chứng từ dữ liệu thật, chỉ đưa những trường cần thiết và che thông tin cá nhân. Mục tiêu là tái hiện phép so sánh, không phải sao chép toàn bộ hồ sơ khách hàng.

## 12. Chỉ mục, phân trang và tính nhất quán nằm ngoài matcher

### 12.1. Cùng kết quả không đồng nghĩa cùng hiệu năng

Hai store có thể cùng trả về `C01, C02, C04` nhưng một nơi dùng chỉ mục hiệu quả, nơi khác phải quét nhiều bản ghi.

Một số yếu tố cần đo:

| Lựa chọn | Tác động có thể gặp |
|---|---|
| `exact()` | Thường phù hợp tra cứu cụ thể, tùy kiểu so sánh và chỉ mục |
| `startsWith()` | Có thể tận dụng chỉ mục phù hợp, tùy cách dịch và store |
| `contains()` hoặc `endsWith()` | Có nguy cơ đọc nhiều dữ liệu vì thiếu tiền tố cố định |
| `ignoreCase()` | Có thể làm thay đổi biểu thức truy vấn và khả năng dùng chỉ mục |
| Regex | Phụ thuộc mẫu, cách neo và đặc tính của store |

Không thể chứng minh hiệu năng chỉ bằng kiểm tra nội dung matcher.

### 12.2. Phân trang không sửa điều kiện lọc

~~~java
repository.findAll(
    example,
    PageRequest.of(
        0,
        20,
        Sort.by("displayName").ascending()
            .and(Sort.by("id").ascending())
    )
);
~~~

Ví dụ giả định repository có phương thức QBE nhận `Pageable`, chẳng hạn `JpaRepository`, và kiểu miền có thuộc tính `id` dùng được để sắp xếp.

Thứ tự có thêm khóa phân biệt giúp xác định vị trí giữa các bản ghi trùng tên trong một tập dữ liệu cố định. Nó không biến truy vấn thành snapshot bất biến khi dữ liệu đang được thêm hoặc sửa.

Thông tin tổng số phần tử của một `Page` cũng có thể cần truy vấn đếm riêng tùy cách thực thi. Tính nhất quán giữa các lần đọc phụ thuộc giao dịch và store, không do `ExampleMatcher` quyết định.

## 13. Khi nào cần một cơ chế truy vấn khác?

QBE phù hợp với biểu mẫu lọc theo các giá trị mẫu và các quy tắc khớp được module hỗ trợ.

Nên chuyển sang cơ chế khác khi yêu cầu gồm:

- Nhóm điều kiện như `active = true AND (name khớp q OR email khớp q)`.
- Khoảng số, khoảng ngày hoặc phép so sánh lớn hơn, nhỏ hơn.
- Điều kiện collection, map hoặc cấu trúc mà QBE không hỗ trợ.
- Phân biệt sự tồn tại của trường với giá trị null.
- Regex trên một module không hỗ trợ regex qua QBE.
- Tìm kiếm toàn văn, xếp hạng độ liên quan hoặc phân tích ngôn ngữ.
- Phép so sánh đặc thù của store mà matcher không diễn đạt đủ.

Trong ứng dụng JPA, có thể cân nhắc Specification hoặc truy vấn được khai báo. Trong MongoDB, có thể dùng truy vấn hoặc API tiêu chí phù hợp của module. Lựa chọn cụ thể dựa trên biểu thức cần diễn đạt và khả năng kho dữ liệu.

Abstraction dùng chung hữu ích khi nó mô tả đủ yêu cầu. Việc chọn API đặc thù cho một yêu cầu vượt phạm vi QBE là một quyết định thiết kế hợp lý.

## 14. Bài tập đối chiếu

Với store của ứng dụng, thực hiện các bước sau:

1. Viết một câu mô tả chính sách cho tên, email, trạng thái và mã tài khoản.
2. Tạo probe chỉ có các thuộc tính thuộc chính sách đó.
3. Chạy các tình huống trong bảng dữ liệu ở mục 10; đối chiếu tập khóa kết quả.
4. Thêm dữ liệu hoa/thường, có dấu, null và chuỗi rỗng để xác định ranh giới hành vi.
5. Quan sát ít nhất một truy vấn được sinh ra; chỉ ra phần nào tương ứng với mỗi điều kiện trong matcher.
6. Chọn một tình huống có kết quả phụ thuộc store, rồi ghi rõ chính sách mà ứng dụng thực sự cần.
7. Kiểm tra liệu QBE có diễn đạt đủ chính sách ấy hay phải dùng truy vấn khác.

Hoàn thành bảng ghi nhận:

| Tình huống | Ý nghĩa matcher | Hành vi quan sát | Có đạt yêu cầu nghiệp vụ? | Điều chỉnh |
|---|---|---|---|---|
| Tên theo tiền tố, bỏ qua hoa/thường | Ghi trước khi chạy | Ghi tập khóa thực tế | Có/Không | Matcher, dữ liệu hoặc truy vấn |
| Mã phân biệt hoa/thường | Ghi trước khi chạy | Ghi quy tắc so sánh thực tế | Có/Không | Ánh xạ, collation hoặc truy vấn |
| Email null | Ghi trước khi chạy | Phân biệt null và thiếu trường nếu có | Có/Không | Chính sách null hoặc API khác |
| Thành phố không dấu | Ghi trước khi chạy | Ghi kết quả với chuỗi có dấu | Có/Không | Chuẩn hóa hoặc tìm kiếm chuyên biệt |

Điều cần hình thành là thói quen nối yêu cầu nghiệp vụ với bằng chứng thực thi: probe cho biết giá trị, matcher cho biết quy tắc, module cho biết khả năng chuyển đổi và store cho biết phép so sánh thực tế. Khi bốn phần đó được đối chiếu rõ ràng, việc dùng Query by Example trở nên có thể giải thích, kiểm chứng và bảo trì khi ứng dụng đổi môi trường lưu trữ.
