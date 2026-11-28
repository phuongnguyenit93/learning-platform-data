# Mô tả tham số bằng @ToolParam

`@ToolParam` giúp mô tả ý nghĩa và tính bắt buộc của từng tham số trong một phương thức công cụ của Spring AI. Khi ứng dụng công bố phương thức được đánh dấu `@Tool`, Spring AI tạo định nghĩa công cụ cùng JSON Schema đầu vào để gửi cho mô hình. Mô hình dựa vào tên, kiểu dữ liệu và mô tả tham số để quyết định có gọi công cụ hay không và tạo dữ liệu đầu vào phù hợp.

Mô tả tốt giúp mô hình hiểu tham số cần giá trị gì, theo định dạng nào và có thể bỏ qua trong trường hợp nào. Tuy nhiên, `@ToolParam` chỉ mô tả hợp đồng đầu vào cho quá trình tool calling. Ứng dụng vẫn phải kiểm tra dữ liệu, xác thực quyền và áp dụng quy tắc nghiệp vụ trước khi thực hiện thao tác.

## `@ToolParam` nằm ở đâu trong định nghĩa công cụ?

Spring AI dùng `@Tool` để đánh dấu một phương thức có thể được mô hình yêu cầu thực thi. `@ToolParam` được đặt trên từng tham số của phương thức đó. Hai annotation có vai trò khác nhau:

| Annotation | Phạm vi | Vai trò |
| --- | --- | --- |
| `@Tool` | Phương thức | Đánh dấu phương thức là công cụ và mô tả mục đích tổng thể của công cụ. |
| `@ToolParam` | Tham số phương thức | Mô tả ý nghĩa của một đầu vào và xác định đầu vào đó có bắt buộc hay không. |

Ví dụ tối giản:

```java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

public class ProductTools {

    @Tool(description = "Tra cứu sản phẩm theo mã SKU")
    public String findProduct(
            @ToolParam(description = "Mã SKU chính xác của sản phẩm cần tra cứu")
            String sku) {
        return "Thông tin sản phẩm: " + sku;
    }
}
```

Trong ví dụ, mô tả ở `@Tool` trả lời câu hỏi “công cụ này làm gì?”, còn mô tả ở `@ToolParam` trả lời câu hỏi “tham số `sku` phải chứa giá trị nào?”. Nếu chỉ mô tả công cụ là “tra cứu sản phẩm” mà không giải thích `sku`, mô hình có thể nhầm mã SKU với tên sản phẩm, tên danh mục hoặc từ khóa tìm kiếm.

## Các thuộc tính của `@ToolParam`

`@ToolParam` cung cấp hai thông tin chính:

- `description`: mô tả ý nghĩa của tham số để mô hình hiểu cách tạo giá trị đầu vào.
- `required`: cho biết tham số có bắt buộc trong schema đầu vào hay không. Mặc định là `true`.

Ví dụ một tham số bắt buộc và một tham số tùy chọn:

```java
@Tool(description = "Tìm kiếm sản phẩm trong danh mục")
public String searchProducts(
        @ToolParam(description = "Từ khóa tên hoặc mã sản phẩm cần tìm")
        String query,
        @ToolParam(
                description = "Số kết quả tối đa cần trả về, từ 1 đến 20; mặc định 10 nếu bỏ qua",
                required = false)
        Integer limit) {

    int effectiveLimit = limit == null ? 10 : limit;
    if (effectiveLimit < 1 || effectiveLimit > 20) {
        throw new IllegalArgumentException("limit phải nằm trong khoảng 1 đến 20");
    }

    return "Tìm kiếm với từ khóa " + query + ", giới hạn " + effectiveLimit;
}
```

`query` là bắt buộc vì `required` mặc định là `true`. `limit` là tùy chọn vì được khai báo `required = false`. Trong ví dụ, `Integer` được dùng thay cho `int` để biểu diễn trường hợp tham số không được cung cấp bằng giá trị `null`.

### Tham số bắt buộc

Khi một tham số phải có mặt trong yêu cầu gọi công cụ, hãy giữ `required = true` hoặc bỏ thuộc tính này vì đó là giá trị mặc định:

```java
@ToolParam(description = "Mã đơn hàng cần tra cứu") String orderId
```

Mô tả nên nói rõ định dạng hoặc phạm vi giá trị nếu có nhiều loại mã định danh. Ví dụ, “mã đơn hàng do hệ thống bán hàng cấp, có dạng ORD-...” hữu ích hơn “mã đơn hàng”.

### Tham số tùy chọn

Khi mô hình có thể bỏ qua một tham số, khai báo `required = false`:

```java
@ToolParam(
    description = "Mã kho cần tra cứu; nếu bỏ qua, hệ thống dùng kho mặc định của người dùng",
    required = false)
String warehouseCode
```

Tính tùy chọn trong schema không tự tạo giá trị mặc định cho Java. Phương thức phải quyết định cách xử lý khi giá trị không được cung cấp. Với kiểu tham chiếu như `String`, `Integer` hoặc `LocalDate`, ứng dụng có thể nhận `null`; với kiểu nguyên thủy như `int` hoặc `boolean`, không thể biểu diễn `null`, vì vậy nên dùng kiểu wrapper nếu cần phân biệt “không được cung cấp” với giá trị `0` hoặc `false`.

`required = false` cũng không có nghĩa tham số được phép chứa mọi giá trị. Nếu người dùng hoặc mô hình cung cấp một giá trị, ứng dụng vẫn phải kiểm tra giá trị đó theo quy tắc nghiệp vụ.

## Viết mô tả tham số rõ ràng

Mô hình chỉ nhìn thấy thông tin được đưa vào định nghĩa công cụ và ngữ cảnh hội thoại. Một mô tả tốt cần đủ cụ thể để phân biệt tham số với các khái niệm gần giống nhau.

Nên làm rõ các khía cạnh sau khi chúng có ý nghĩa với nghiệp vụ:

1. **Ý nghĩa:** tham số đại diện cho mã định danh, tên, từ khóa, số lượng hay một mốc thời gian?
2. **Định dạng:** chuỗi có tiền tố nào, ngày theo định dạng nào, số tiền dùng đơn vị gì?
3. **Phạm vi:** giá trị hợp lệ có giới hạn, tập lựa chọn hoặc quy tắc nào?
4. **Ngữ cảnh:** giá trị áp dụng cho người dùng, kho, tenant, múi giờ hoặc loại tài nguyên nào?
5. **Tính tùy chọn:** nếu bỏ qua, hệ thống dùng mặc định nào hoặc áp dụng hành vi nào?

Ví dụ so sánh:

| Mô tả yếu | Mô tả rõ hơn |
| --- | --- |
| `Mã` | `Mã SKU chính xác của sản phẩm, ví dụ SKU-100; không phải tên sản phẩm.` |
| `Ngày bắt đầu` | `Ngày bắt đầu lọc dữ liệu, theo định dạng YYYY-MM-DD và tính theo múi giờ của cửa hàng.` |
| `Số lượng` | `Số sản phẩm cần lấy, là số nguyên từ 1 đến 50.` |
| `Trạng thái` | `Trạng thái đơn hàng cần lọc: PENDING, CONFIRMED hoặc CANCELLED.` |
| `Từ khóa` | `Cụm từ dùng để tìm trong tên sản phẩm hoặc mô tả; không nhập mã SKU ở tham số này.` |

Mô tả nên ngắn, trực tiếp và tập trung vào một tham số. Không nên chép toàn bộ quy trình nghiệp vụ, chính sách bảo mật hoặc hướng dẫn hội thoại vào mọi `description`. Phần mô tả công cụ nên giải thích mục đích chung; mô tả tham số nên giải thích dữ liệu cụ thể.

### Nêu định dạng, đơn vị và múi giờ

Các giá trị như ngày, thời gian, tiền tệ và khoảng đo rất dễ bị hiểu sai nếu thiếu ngữ cảnh. Hãy nêu rõ định dạng và đơn vị:

```java
@Tool(description = "Tìm các lịch hẹn trong một khoảng thời gian")
public String findAppointments(
        @ToolParam(description = "Ngày bắt đầu, định dạng ISO YYYY-MM-DD")
        LocalDate fromDate,
        @ToolParam(description = "Ngày kết thúc, định dạng ISO YYYY-MM-DD; phải bằng hoặc sau ngày bắt đầu")
        LocalDate toDate,
        @ToolParam(description = "Múi giờ IANA dùng để diễn giải ngày, ví dụ Asia/Ho_Chi_Minh")
        String timeZone) {

    if (toDate.isBefore(fromDate)) {
        throw new IllegalArgumentException("Ngày kết thúc phải bằng hoặc sau ngày bắt đầu");
    }
    return "Tra cứu lịch hẹn";
}
```

Kiểu Java và schema được tạo cần tương thích với khả năng chuyển đổi của phiên bản Spring AI và provider đang dùng. Với dữ liệu thời gian, hãy kiểm tra cả định dạng mà mô hình gửi và cách ứng dụng chuyển đổi trước khi gọi service.

### Mô tả giới hạn và tập giá trị

Nếu tham số chỉ nhận một số lựa chọn, mô tả rõ tập giá trị và ý nghĩa của từng giá trị. Ví dụ:

```java
@ToolParam(
    description = "Thứ tự sắp xếp kết quả: PRICE_ASC (giá tăng dần), PRICE_DESC (giá giảm dần), NAME_ASC (tên A-Z)")
String sortBy
```

Nếu dùng `enum` trong Java, kiểu dữ liệu này có thể giúp thể hiện tập lựa chọn hữu hạn trong schema được sinh ra. Dù dùng `enum` hay `String`, ứng dụng vẫn cần xử lý trường hợp dữ liệu không thể chuyển đổi hoặc giá trị không được chấp nhận. Không nên chỉ dựa vào mô tả ngôn ngữ tự nhiên để giới hạn dữ liệu.

## Schema đầu vào được hình thành như thế nào?

Spring AI sử dụng chữ ký phương thức, kiểu Java và metadata annotation để tạo schema đầu vào cho công cụ. Schema mô tả cấu trúc dữ liệu mà mô hình cần gửi khi gọi công cụ. Với ví dụ tìm kiếm ở trên, schema có thể được hình dung đơn giản như sau:

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Từ khóa tên hoặc mã sản phẩm cần tìm"
    },
    "limit": {
      "type": "integer",
      "description": "Số kết quả tối đa cần trả về, từ 1 đến 20; mặc định 10 nếu bỏ qua"
    }
  },
  "required": ["query"]
}
```

Đây là minh họa khái niệm về cấu trúc schema, không phải cam kết rằng mọi provider sẽ nhận đúng chuỗi schema giống hệt. Integration có thể chuẩn hóa hoặc chuyển đổi schema theo API của nhà cung cấp. Điểm quan trọng là `query` được đánh dấu bắt buộc, `limit` có thể vắng mặt, và mô tả từng thuộc tính đi cùng định nghĩa công cụ.

Mô hình dùng schema để tạo tool call. Sau đó Spring AI chuyển dữ liệu đầu vào sang kiểu tham số của phương thức và gọi callback. Schema hỗ trợ mô hình tạo dữ liệu đúng hình dạng; nó không thay thế xác thực ở runtime. Ví dụ, mô tả `limit` từ 1 đến 20 không đảm bảo mọi phản hồi đều nằm trong khoảng đó.

## Tên tham số và metadata biên dịch Java

Tên tham số trong chữ ký phương thức cũng góp phần làm rõ schema. Hãy đặt tên có nghĩa như `orderId`, `fromDate`, `warehouseCode` thay vì `a`, `value` hoặc `param1`.

Để framework có thể đọc tên tham số từ reflection một cách đáng tin cậy, dự án Java nên giữ metadata tên tham số khi biên dịch bằng tùy chọn `-parameters`. Với Maven Compiler Plugin, có thể cấu hình:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Với Gradle:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
```

Sau khi thay đổi cấu hình biên dịch, cần build lại lớp chứa phương thức công cụ. Hãy kiểm tra schema thực tế hoặc kiểm thử callback để xác nhận tên thuộc tính được tạo đúng như mong muốn.

## Thiết kế chữ ký phương thức dễ gọi

Một công cụ tốt thường có số lượng tham số vừa đủ, kiểu dữ liệu rõ ràng và trách nhiệm tập trung. Nếu một phương thức nhận quá nhiều chuỗi không phân biệt được, mô hình dễ truyền nhầm giá trị.

Ví dụ một phương thức có nhiều tham số nhưng mô tả mơ hồ:

```java
@Tool(description = "Tìm kiếm dữ liệu")
public String search(String value, String type, String code, String option) {
    // Logic tìm kiếm
    return "...";
}
```

Có thể làm rõ mục đích và đầu vào:

```java
@Tool(description = "Tra cứu đơn hàng theo mã đơn và bộ lọc trạng thái tùy chọn")
public String findOrders(
        @ToolParam(description = "Mã đơn hàng chính xác, ví dụ ORD-2026-001")
        String orderId,
        @ToolParam(description = "Trạng thái cần lọc: PENDING, CONFIRMED hoặc CANCELLED; bỏ qua để lấy mọi trạng thái", required = false)
        String status) {
    // Kiểm tra dữ liệu rồi gọi service nghiệp vụ
    return "...";
}
```

Nếu đầu vào là một nhóm dữ liệu có cấu trúc và có quan hệ với nhau, có thể cân nhắc một kiểu DTO riêng thay vì tạo danh sách dài các tham số rời rạc. Khi dùng DTO hoặc kiểu lồng nhau, cần kiểm tra schema mà phiên bản Spring AI thực tế sinh ra, đặc biệt với trường tùy chọn, collection, enum và kiểu ngày giờ.

## Kết hợp `@ToolParam` với `ToolContext`

Không phải dữ liệu mà phương thức công cụ nhận được đều nên do mô hình tạo ra. `ToolContext` dành cho ngữ cảnh do ứng dụng cung cấp, chẳng hạn principal đã xác thực, tenant hiện tại hoặc trace ID. Đây là dữ liệu tin cậy từ luồng ứng dụng và không phải tham số người dùng cần điền trong JSON tool call.

Ví dụ khái niệm:

```java
@Tool(description = "Tra cứu các đơn hàng của người dùng hiện tại")
public String findMyOrders(
        @ToolParam(description = "Trạng thái đơn hàng cần lọc; bỏ qua để lấy mọi trạng thái", required = false)
        String status,
        ToolContext toolContext) {

    String userId = (String) toolContext.getContext().get("userId");
    // Xác minh ngữ cảnh và gọi service theo userId đã được ứng dụng xác thực
    return "Các đơn hàng của người dùng hiện tại";
}
```

`ToolContext` là tham số đặc biệt được Spring AI cung cấp cho callback và không nên mô tả như đầu vào do mô hình lựa chọn. Trong khi đó, `status` là dữ liệu mô hình có thể đề xuất nên dùng `@ToolParam`. Service vẫn cần xác thực ngữ cảnh và kiểm tra quyền truy cập; không coi sự hiện diện của `userId` trong context là bằng chứng tự thân nếu ứng dụng chưa xác thực nguồn gốc của nó.

## Xác thực dữ liệu sau khi nhận tool call

Mô hình có thể tạo JSON hợp lệ về cú pháp nhưng sai về nghiệp vụ. Vì vậy, phương thức công cụ hoặc service phía sau phải kiểm tra đầu vào trước khi thực hiện hành động.

- Kiểm tra chuỗi rỗng, khoảng trắng, độ dài tối đa và định dạng mã định danh.
- Kiểm tra số nằm trong giới hạn, ngày hợp lệ và ngày bắt đầu không sau ngày kết thúc.
- Kiểm tra enum hoặc tập giá trị được phép trước khi chuyển thành truy vấn hay lệnh nghiệp vụ.
- Kiểm tra tài nguyên có tồn tại và thuộc phạm vi người dùng/tenant được phép truy cập.
- Với thao tác ghi, kiểm tra trạng thái hiện tại, quyền, xác nhận và tính idempotent theo yêu cầu nghiệp vụ.

Ví dụ kiểm tra thủ công:

```java
private void validateSku(String sku) {
    if (sku == null || sku.isBlank()) {
        throw new IllegalArgumentException("SKU không được để trống");
    }
    if (!sku.matches("SKU-[A-Z0-9-]{3,30}")) {
        throw new IllegalArgumentException("SKU không đúng định dạng");
    }
}
```

Có thể dùng Bean Validation hoặc cơ chế kiểm tra miền hiện có của dự án. Dù chọn cách nào, việc kiểm tra phải diễn ra ở phía ứng dụng và service. Không nên tin rằng mô hình sẽ luôn tuân thủ mô tả hoặc schema.

## Những lỗi thường gặp khi mô tả tham số

| Hiện tượng | Nguyên nhân thường gặp | Cách cải thiện |
| --- | --- | --- |
| Mô hình truyền tên sản phẩm vào tham số mã SKU | Mô tả không phân biệt mã định danh và tên hiển thị | Nêu rõ ý nghĩa, ví dụ và dữ liệu không thuộc tham số. |
| Mô hình bỏ qua tham số cần thiết | Tham số bị đánh dấu `required = false` hoặc mô tả không giải thích vì sao cần | Đặt `required = true` và mô tả mục đích cụ thể. |
| Tham số tùy chọn gây lỗi null | Mã xử lý giả định tham số luôn có giá trị | Dùng kiểu tham chiếu, xử lý `null` và xác định giá trị mặc định ở ứng dụng. |
| Ngày bị hiểu sai | Không nêu định dạng hoặc múi giờ | Ghi định dạng ngày/giờ và quy tắc múi giờ trong mô tả. |
| Giá trị vượt giới hạn | Chỉ ghi giới hạn trong description mà không kiểm tra runtime | Kiểm tra phạm vi trong callback hoặc service. |
| Schema có tên thuộc tính khó hiểu | Tên biến chung chung hoặc thiếu metadata tên tham số | Đặt tên rõ nghĩa và bật tùy chọn biên dịch `-parameters`. |
| Mô hình chọn nhầm công cụ | Mô tả công cụ và mô tả tham số trùng lặp hoặc quá chung | Phân biệt mục đích từng công cụ và trách nhiệm của từng tham số. |

Khi điều tra lỗi, nên xem xét cả ba lớp: mô tả và schema được gửi cho mô hình, JSON mà mô hình trả về, và bước chuyển đổi/kiểm tra dữ liệu trong ứng dụng. Cách này giúp xác định lỗi nằm ở lựa chọn công cụ, cách tạo tham số hay logic thực thi.

## Kiểm thử định nghĩa tham số và callback

Kiểm thử nên xác nhận cả metadata lẫn hành vi thực thi:

1. **Kiểm tra metadata:** xác nhận tên tham số, kiểu dữ liệu, description và danh sách trường bắt buộc trong schema được tạo ra.
2. **Kiểm tra tham số bắt buộc:** thử thiếu tham số bắt buộc hoặc truyền giá trị rỗng; xác nhận yêu cầu bị từ chối phù hợp.
3. **Kiểm tra tham số tùy chọn:** thử bỏ qua tham số, truyền `null` nếu luồng chuyển đổi cho phép, và truyền giá trị hợp lệ; xác nhận mặc định do ứng dụng áp dụng đúng.
4. **Kiểm tra biên:** thử số âm, số vượt giới hạn, chuỗi quá dài, ngày không hợp lệ và enum không được hỗ trợ.
5. **Kiểm tra quyền:** thử mã tài nguyên của người dùng khác hoặc tenant khác; xác nhận service từ chối truy cập.
6. **Kiểm tra tích hợp:** dùng model giả hoặc phản hồi tool call kiểm soát được để xác nhận JSON đầu vào được ánh xạ đúng đến tham số phương thức.

Không nên chỉ dựa vào một lần gọi mô hình thật để kết luận annotation hoạt động đúng. Kiểm thử schema và callback trực tiếp giúp kết quả ổn định, ít phụ thuộc vào cách diễn đạt ngẫu nhiên của mô hình. Sau đó có thể chạy thêm kiểm thử tích hợp với model thật để đánh giá chất lượng mô tả.

## Nguyên tắc ghi nhớ

- Dùng `@Tool` để mô tả mục đích tổng thể của phương thức công cụ.
- Dùng `@ToolParam(description = ...)` để giải thích chính xác từng đầu vào.
- Giữ `required = true` cho dữ liệu bắt buộc; dùng `required = false` cho dữ liệu có thể bỏ qua.
- Với tham số tùy chọn, xử lý trường hợp không có giá trị trong mã ứng dụng; annotation không tự đặt giá trị mặc định.
- Đặt tên biến rõ nghĩa, nêu định dạng/đơn vị/phạm vi khi cần và kiểm tra schema được sinh ra.
- Dùng `ToolContext` cho ngữ cảnh do ứng dụng cung cấp, không biến danh tính và quyền truy cập thành tham số do mô hình tự chọn.
- Luôn xác thực đầu vào và quyền ở phía ứng dụng trước khi gọi service hoặc thực hiện tác động phụ.

`@ToolParam` làm cho hợp đồng đầu vào dễ hiểu hơn đối với mô hình và người phát triển. Khi mô tả rõ ràng, schema phù hợp và kiểm tra runtime đầy đủ, công cụ sẽ dễ được gọi đúng, dễ kiểm thử và an toàn hơn khi kết nối với dịch vụ nghiệp vụ.
