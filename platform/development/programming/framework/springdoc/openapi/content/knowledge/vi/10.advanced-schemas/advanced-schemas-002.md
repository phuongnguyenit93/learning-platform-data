# Generic, lớp bao phản hồi và nguy cơ mất thông tin kiểu

API thường dùng các kiểu dữ liệu tổng quát để tái sử dụng cấu trúc: một lớp bao phản hồi có thể chứa sách, tác giả hoặc đơn hàng; một cấu trúc phân trang có thể chứa danh sách phần tử thuộc nhiều kiểu; một request hàng loạt có thể nhận danh sách DTO khác nhau. Trong Java, các cấu trúc này được biểu diễn bằng **generic type**. Khi springdoc-openapi tạo schema, thư viện cần xác định kiểu cụ thể được đặt vào tham số generic để mô tả đúng JSON trên HTTP.

Vấn đề xuất hiện khi kiểu cụ thể không còn thể hiện rõ trong chữ ký method hoặc metadata bytecode. Java dùng **type erasure** để thực thi generic, nên thông tin tham số kiểu không tồn tại như một kiểu runtime riêng cho từng instance. Tuy nhiên, chữ ký generic khai báo trong class file vẫn có thể lưu metadata **Signature** để reflection và công cụ phân tích đọc được. Vì vậy, cần phân biệt việc Java xóa tham số kiểu khỏi runtime object với việc thông tin generic trong khai báo method/class vẫn có thể được đọc.

Với springdoc-openapi, cách khai báo kiểu trả về, cách thiết kế lớp bao và cách dùng annotation có thể quyết định schema được tạo có đầy đủ hay chỉ còn **Object**, raw type hoặc một cấu trúc không phản ánh JSON thực tế. Bài này đi từ generic cơ bản đến wrapper response, type erasure, cách biểu diễn trong OpenAPI và quy trình xác minh đặc tả.

## 1. Generic type trong Java và ý nghĩa với API

Generic cho phép một lớp hoặc method làm việc với nhiều kiểu dữ liệu mà vẫn giữ thông tin kiểu ở thời điểm biên dịch.

~~~java
public class Box<T> {
    private T value;

    public Box(T value) {
        this.value = value;
    }

    public T getValue() {
        return value;
    }
}
~~~

**Box<String>** chứa String, còn **Box<BookResponse>** chứa BookResponse. Cùng một định nghĩa **Box<T>** được tái sử dụng mà không cần viết hai lớp riêng.

Một lớp bao phản hồi có thể khai báo tham số kiểu T, chẳng hạn **ApiEnvelope<T>**, để property data giữ kiểu cụ thể do từng operation lựa chọn. Phần định nghĩa đầy đủ của wrapper này sẽ xuất hiện ở ví dụ thiết kế response bên dưới.

Các endpoint có thể trả về cùng một cấu trúc bên ngoài nhưng khác kiểu dữ liệu bên trong:

~~~java
ApiEnvelope<BookResponse>
ApiEnvelope<AuthorResponse>
ApiEnvelope<List<BookResponse>>
~~~

Với client, ba kiểu này có cấu trúc JSON bao ngoài tương tự, nhưng kiểu của **data** khác nhau. OpenAPI cần giữ được sự khác biệt đó để người dùng biết trường data chứa object sách, object tác giả hay mảng sách.

### Generic type lồng nhau

Generic có thể lồng nhiều cấp:

~~~java
ApiEnvelope<List<BookResponse>>
ApiEnvelope<PageResponse<BookResponse>>
ApiEnvelope<Map<String, List<BookResponse>>>
~~~

Mỗi cấp đều có ý nghĩa đối với schema:

- **ApiEnvelope** mô tả các trường success, data, error.
- **List** hoặc **PageResponse** mô tả cấu trúc tập hợp.
- **BookResponse** mô tả từng phần tử.
- **Map<String, ...>** mô tả object có các key động và giá trị theo schema xác định.

Nếu một cấp bị mất kiểu cụ thể, schema phía dưới có thể trở thành object chung chung hoặc không mô tả được cấu trúc mà client cần.

## 2. Từ generic method đến schema OpenAPI

Khi kiểu cụ thể xuất hiện trong chữ ký method, công cụ phân tích có thể đọc generic return type và suy ra schema.

~~~java
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping("/{bookId}")
    public ApiEnvelope<BookResponse> getBook(
        @PathVariable UUID bookId
    ) {
        BookResponse book = findBook(bookId);
        return new ApiEnvelope<>(true, book, null);
    }
}
~~~

Chữ ký **ApiEnvelope<BookResponse>** cho biết tham số kiểu T của **ApiEnvelope<T>** được thay bằng **BookResponse** trong operation này. springdoc có thể phân tích chữ ký generic để mô tả data bằng schema của BookResponse.

Đặc tả rút gọn có thể tương tự:

~~~yaml
paths:
  /api/books/{bookId}:
    get:
      responses:
        "200":
          description: Lấy thông tin sách thành công
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelopeBookResponse"
components:
  schemas:
    ApiEnvelopeBookResponse:
      type: object
      properties:
        success:
          type: boolean
        data:
          $ref: "#/components/schemas/BookResponse"
        error:
          $ref: "#/components/schemas/ApiError"
~~~

Tên component ở ví dụ chỉ minh họa. Tên thực tế được springdoc/swagger-core tạo ra phụ thuộc phiên bản, model converter và cấu hình đặt tên. Điều cần kiểm tra là schema của data phải trỏ tới BookResponse, còn các trường bao ngoài vẫn phải được giữ.

### Generic trong request body

Generic cũng có thể dùng cho dữ liệu client gửi:

~~~java
public record BulkRequest<T>(
    List<T> items,
    boolean validateOnly
) {}

@PostMapping("/bulk")
public ApiEnvelope<BulkResult> createMany(
    @Valid @RequestBody BulkRequest<CreateBookRequest> request
) {
    // ...
    return null;
}
~~~

Ở đây items là danh sách CreateBookRequest. Schema request body cần mô tả:

- Object BulkRequest.
- Property items là array.
- items có phần tử theo schema CreateBookRequest.
- Property validateOnly là boolean.

Nếu chữ ký chỉ dùng **BulkRequest** không có tham số kiểu, thông tin phần tử của items không còn rõ trong khai báo method. springdoc có thể chỉ suy ra kiểu thô hoặc object chung, tùy metadata và converter.

## 3. Lớp bao phản hồi và ResponseEntity

Trong Spring Boot, cần phân biệt **lớp bao HTTP** với **lớp bao dữ liệu của ứng dụng**.

**ResponseEntity<T>** là kiểu của Spring dùng để điều khiển status code, header và body HTTP. Nó không nhất thiết là một object JSON được serialize thành các property statusCode, headers và body. Với controller trả **ResponseEntity<ApiEnvelope<BookResponse>>**, body JSON của ứng dụng là ApiEnvelope<BookResponse>.

~~~java
@GetMapping("/{bookId}")
public ResponseEntity<ApiEnvelope<BookResponse>> getBook(
    @PathVariable UUID bookId
) {
    BookResponse book = findBook(bookId);
    ApiEnvelope<BookResponse> body =
        new ApiEnvelope<>(true, book, null);

    return ResponseEntity.ok(body);
}
~~~

springdoc thường xử lý ResponseEntity như wrapper transport của Spring và phân tích kiểu body bên trong. Kết quả cần mô tả ApiEnvelope<BookResponse>, chứ không phải một schema JSON cho chính ResponseEntity.

Ngược lại, **ApiEnvelope<T>** là lớp bao dữ liệu do ứng dụng định nghĩa. Nếu controller trả ApiEnvelope<BookResponse> trực tiếp, hoặc đặt nó bên trong ResponseEntity, các property của envelope là một phần JSON thật và cần xuất hiện trong schema.

| Chữ ký method | Ý nghĩa đối với response body |
|---|---|
| **BookResponse** | JSON là một BookResponse |
| **ResponseEntity<BookResponse>** | HTTP status/header do ResponseEntity điều khiển; body là BookResponse |
| **ApiEnvelope<BookResponse>** | JSON body là envelope có data kiểu BookResponse |
| **ResponseEntity<ApiEnvelope<BookResponse>>** | ResponseEntity điều khiển HTTP; JSON body vẫn là envelope |
| **ResponseEntity<ApiEnvelope>** | Envelope mất tham số kiểu cụ thể trong chữ ký |

Không nên mô tả ResponseEntity như một DTO response. Hãy mô tả kiểu body thực tế và dùng ResponseEntity để điều khiển hành vi HTTP.

## 4. Thiết kế generic wrapper có cấu trúc ổn định

Một wrapper có thể chứa dữ liệu thành công và lỗi:

~~~java
public record ApiError(
    String code,
    String message
) {}

public class ApiEnvelope<T> {
    private final boolean success;
    private final T data;
    private final ApiError error;

    public ApiEnvelope(boolean success, T data, ApiError error) {
        this.success = success;
        this.data = data;
        this.error = error;
    }

    public boolean isSuccess() {
        return success;
    }

    public T getData() {
        return data;
    }

    public ApiError getError() {
        return error;
    }

    public static <T> ApiEnvelope<T> success(T data) {
        return new ApiEnvelope<>(true, data, null);
    }

    public static <T> ApiEnvelope<T> failure(ApiError error) {
        return new ApiEnvelope<>(false, null, error);
    }
}
~~~

Một response thành công:

~~~json
{
  "success": true,
  "data": {
    "id": "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001",
    "title": "Spring in Action"
  },
  "error": null
}
~~~

Một response lỗi:

~~~json
{
  "success": false,
  "data": null,
  "error": {
    "code": "BOOK_NOT_FOUND",
    "message": "Không tìm thấy sách"
  }
}
~~~

Nếu API luôn trả wrapper, schema phải mô tả cả cấu trúc ngoài lẫn phần data. Chỉ khai báo response là BookResponse sẽ làm tài liệu sai với JSON thực tế vì client còn nhận success và error.

### Không biến mọi response thành Object

Một thiết kế dễ gây mất thông tin là:

~~~java
public record ApiEnvelope(
    boolean success,
    Object data,
    ApiError error
) {}
~~~

Kiểu Object khiến schema của data rất rộng. Client không biết khi nào data là BookResponse, khi nào là AuthorResponse hoặc một collection. Nếu từng endpoint có kiểu cụ thể, generic ApiEnvelope<T> giúp giữ quan hệ kiểu trong chữ ký method và tái sử dụng cấu trúc.

Nếu dữ liệu thực sự có nhiều dạng không thể biết trước, hãy mô tả hợp đồng bằng oneOf/anyOf hoặc một mô hình đa hình có discriminator khi phù hợp. Object chỉ nên dùng khi payload thực sự không có cấu trúc ổn định và điều đó được chấp nhận trong hợp đồng.

## 5. Type erasure: điều Java giữ và điều Java xóa

Java triển khai generic bằng **type erasure**. Ở mức bytecode thực thi, tham số kiểu được thay bằng kiểu giới hạn (bound) của nó; nếu không khai báo bound, giới hạn mặc định là Object. Vì vậy, **ApiEnvelope<BookResponse>** và **ApiEnvelope<AuthorResponse>** cùng có class runtime là ApiEnvelope.

~~~java
ApiEnvelope<String> texts =
    new ApiEnvelope<>(true, "hello", null);

ApiEnvelope<Integer> counts =
    new ApiEnvelope<>(true, 42, null);

System.out.println(texts.getClass() == counts.getClass()); // true
~~~

Một instance không mang theo một class runtime riêng cho từng tham số generic. Từ texts.getClass() không thể hỏi trực tiếp rằng instance này là ApiEnvelope<String>.

Tuy nhiên, không nên kết luận rằng mọi thông tin generic đều biến mất khỏi file .class. Trình biên dịch thường ghi **generic Signature metadata** cho khai báo class, field, method và superclass. Java Reflection có thể đọc chữ ký generic của method:

~~~java
Method method = BookController.class.getMethod(
    "getBook",
    UUID.class
);

Type returnType = method.getGenericReturnType();
System.out.println(returnType);
~~~

getGenericReturnType() có thể trả về một ParameterizedType tương ứng với ApiEnvelope<BookResponse>, trong khi getReturnType() chỉ trả về class runtime ApiEnvelope. Đây là lý do springdoc có thể phân tích generic type được khai báo ở method dù Java thực thi bằng type erasure.

| Reflection API | Thông tin |
|---|---|
| **Method.getReturnType()** | Kiểu class đã xóa generic, ví dụ ApiEnvelope |
| **Method.getGenericReturnType()** | Chữ ký generic nếu metadata còn, ví dụ ApiEnvelope<BookResponse> |
| **Field.getType()** | Kiểu runtime của field sau erasure |
| **Field.getGenericType()** | Chữ ký generic của field nếu được lưu |
| **Class.getGenericSuperclass()** | Kiểu superclass cùng tham số generic được khai báo |

Vì vậy, rủi ro không chỉ là type erasure của Java. Rủi ro thực tế là chữ ký API được khai báo quá thô, không giữ specialization cụ thể hoặc metadata cần thiết không thể xác định được.

## 6. Những cách khai báo làm mất thông tin kiểu

Các trường hợp dưới đây khiến công cụ sinh tài liệu khó xác định schema cụ thể:

### Raw type

~~~java
@GetMapping("/books")
public ApiEnvelope getBooks() {
    // ...
    return null;
}
~~~

Method chỉ khai báo ApiEnvelope, không có T. Generic parameter đã bị bỏ khỏi chữ ký. Schema data có thể trở thành object không xác định hoặc một dạng chung chung.

### Dùng Object

~~~java
public ApiEnvelope<Object> getData() {
    // ...
    return null;
}
~~~

Chữ ký có generic nhưng kiểu cụ thể vẫn là Object. Metadata không cho biết payload thực tế có hình dạng gì.

### Wildcard không xác định được kiểu cụ thể

~~~java
public ApiEnvelope<?> getData() {
    // ...
    return null;
}
~~~

Wildcard ? cho biết có một kiểu nào đó nhưng không chỉ ra DTO cụ thể. ? extends SomeBase có thể cung cấp một upper bound, nhưng upper bound không nhất thiết thể hiện đầy đủ các property của kiểu runtime cụ thể. Nếu hợp đồng có nhiều dạng, hãy mô tả chúng có chủ đích bằng oneOf hoặc discriminator.

### Type variable chưa được specialization

~~~java
@GetMapping("/data")
public <T> ApiEnvelope<T> getData() {
    // ...
    return null;
}
~~~

Method type variable T chưa được ràng buộc với một kiểu cụ thể trong chữ ký endpoint. springdoc không thể tự đoán payload runtime từ dữ liệu mà method sẽ trả về.

### Trả về generic qua interface hoặc base class không có kiểu cụ thể

~~~java
public interface ResultProvider<T> {
    ApiEnvelope<T> getResult();
}

public class GenericController<T> {
    public ApiEnvelope<T> getResult() {
        // ...
        return null;
    }
}
~~~

Nếu endpoint được mô tả từ một khai báo generic mà T không được xác định trong ngữ cảnh controller cụ thể, schema có thể không được phân giải như mong muốn. Khi controller kế thừa một base class đã specialization, metadata superclass có thể cung cấp thông tin, nhưng cần kiểm tra kết quả thực tế theo cấu trúc kế thừa và phiên bản thư viện.

## 7. Cách giữ lại kiểu cụ thể cho generic wrapper

Ưu tiên đầu tiên là khai báo kiểu cụ thể ngay trong chữ ký method:

~~~java
@GetMapping("/{bookId}")
public ApiEnvelope<BookResponse> getBook(
    @PathVariable UUID bookId
) {
    return ApiEnvelope.success(findBook(bookId));
}
~~~

Nếu controller dùng lớp cha generic, tạo controller chuyên biệt với kiểu cụ thể:

~~~java
public abstract class BaseReadController<T> {
    public abstract ApiEnvelope<T> getOne(UUID id);
}

@RestController
@RequestMapping("/api/books")
public class BookController
        extends BaseReadController<BookResponse> {

    @Override
    @GetMapping("/{bookId}")
    public ApiEnvelope<BookResponse> getOne(
        @PathVariable UUID bookId
    ) {
        return ApiEnvelope.success(findBook(bookId));
    }
}
~~~

Việc override method bằng chữ ký đã specialization giúp hợp đồng của controller thể hiện rõ BookResponse. Nếu giữ method chỉ có T ở một lớp cha, hãy kiểm tra springdoc có giải quyết được kiểu kế thừa trong trường hợp cụ thể hay không.

### Dùng concrete subclass cho một response ổn định

Nếu muốn có tên schema rõ ràng cho một kiểu wrapper cụ thể, có thể tạo lớp chuyên biệt:

~~~java
@Schema(
    name = "BookEnvelope",
    description = "Phản hồi chứa thông tin sách"
)
public class BookEnvelope extends ApiEnvelope<BookResponse> {
    public BookEnvelope(
        boolean success,
        BookResponse data,
        ApiError error
    ) {
        super(success, data, error);
    }
}
~~~

Sau đó controller có thể trả về BookEnvelope. Generic superclass khai báo ApiEnvelope<BookResponse> nên kiểu cụ thể được lưu trong metadata của superclass. Cách này hữu ích khi cần tên component ổn định hoặc muốn một kiểu response chuyên biệt cho tài liệu.

Một concrete subclass cần phản ánh JSON thực tế. Không tạo lớp chỉ để làm tài liệu trông đẹp nếu serializer không tạo ra cấu trúc tương ứng.

## 8. Phân trang và collection trong generic wrapper

Một kiểu phân trang tùy biến có thể dùng generic:

~~~java
public record PageResponse<T>(
    List<T> items,
    int page,
    int size,
    long totalElements,
    int totalPages
) {}
~~~

Controller:

~~~java
@GetMapping
public ApiEnvelope<PageResponse<BookResponse>> listBooks(
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") int size
) {
    PageResponse<BookResponse> result = searchBooks(page, size);
    return ApiEnvelope.success(result);
}
~~~

Schema cần thể hiện các cấp:

~~~yaml
ApiEnvelope:
  type: object
  properties:
    success:
      type: boolean
    data:
      $ref: "#/components/schemas/PageResponseBookResponse"

PageResponseBookResponse:
  type: object
  properties:
    items:
      type: array
      items:
        $ref: "#/components/schemas/BookResponse"
    page:
      type: integer
    size:
      type: integer
    totalElements:
      type: integer
      format: int64
    totalPages:
      type: integer
~~~

Tên component minh họa có thể khác trong output thật. Quan trọng là items phải trỏ tới BookResponse, không phải Object.

Với Spring Data, Page<T> mang metadata phân trang và các chi tiết phụ thuộc implementation. Để hợp đồng API ổn định, nhiều hệ thống chuyển Page<T> thành DTO PageResponse<T> với những trường công khai đã chọn. Khi đó schema ít phụ thuộc hơn vào cấu trúc nội bộ của Spring Data.

## 9. Dùng @Schema(implementation = ...) đúng phạm vi

Annotation **@Schema(implementation = SomeClass.class)** có thể chỉ định kiểu schema được dùng trong tài liệu. Cách này hữu ích khi kiểu trả về Java quá tổng quát hoặc khi muốn chỉ rõ một DTO concrete.

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Thông tin sách",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = BookEnvelope.class)
    )
)
@GetMapping("/{bookId}")
public ResponseEntity<?> getBook(@PathVariable UUID bookId) {
    // Trả về JSON có đúng cấu trúc BookEnvelope
    return ResponseEntity.ok(loadBookEnvelope(bookId));
}
~~~

Trong ví dụ, tài liệu dùng BookEnvelope làm schema response. Chữ ký ResponseEntity<?> vẫn không cung cấp kiểu body cụ thể cho công cụ suy luận; annotation chỉ bổ sung thông tin cho tài liệu. Kiểu dữ liệu thực tế phải luôn tương thích với BookEnvelope.

implementation nhận một class literal, vì vậy không thể viết trực tiếp **ApiEnvelope<BookResponse>.class** trong Java. Java không cho phép lấy class literal của một parameterized type. Các lựa chọn thường dùng:

- Khai báo kiểu generic cụ thể trong chữ ký method để springdoc suy ra.
- Tạo concrete subclass như BookEnvelope để có class literal và tên component rõ ràng.
- Dùng @ApiResponse/@Content/@Schema để chỉ định schema concrete khi cần ghi đè tài liệu, đồng thời bảo đảm JSON runtime có cấu trúc tương ứng.

Không dùng **@Schema(implementation = BookResponse.class)** nếu response thật là ApiEnvelope<BookResponse>. Cách đó sẽ làm mất các trường success, data và error khỏi schema được công bố.

### Khi cần dùng useReturnTypeSchema

Trong một số trường hợp khai báo @ApiResponse thủ công, có thể cần để springdoc sử dụng schema suy ra từ kiểu trả về thay vì schema mặc định từ phần mô tả. Thuộc tính **useReturnTypeSchema** của @ApiResponse có thể hữu ích tùy phiên bản swagger-annotations và cách khai báo response. Hãy kiểm tra Javadoc của phiên bản dependency đang dùng và xác minh kết quả JSON; đừng thêm thuộc tính này một cách máy móc nếu schema đã được suy ra đúng.

## 10. Generic request và response nên giữ hợp đồng nhất quán

Một API có thể dùng cùng kiểu generic ở cả request và response:

~~~java
public record DataRequest<T>(
    T data
) {}

public record DataResponse<T>(
    boolean accepted,
    T result
) {}
~~~

Controller:

~~~java
@PostMapping("/books/validate")
public DataResponse<BookResponse> validateBook(
    @RequestBody DataRequest<CreateBookRequest> request
) {
    // ...
    return null;
}
~~~

Request schema cần có data theo CreateBookRequest; response schema cần có result theo BookResponse. Không nên tái sử dụng một schema DataRequest<Object> hoặc DataResponse<Object> nếu endpoint thực tế có DTO cụ thể.

Với API có nhiều loại dữ liệu, có thể dùng nhiều endpoint specialization khác nhau. Ví dụ:

| Endpoint | Kiểu request | Kiểu response |
|---|---|---|
| POST /api/books | **DataRequest<CreateBookRequest>** | **DataResponse<BookResponse>** |
| POST /api/authors | **DataRequest<CreateAuthorRequest>** | **DataResponse<AuthorResponse>** |
| POST /api/orders | **DataRequest<CreateOrderRequest>** | **DataResponse<OrderResponse>** |

Như vậy, cấu trúc wrapper được tái sử dụng nhưng từng operation vẫn có schema cụ thể.

## 11. Đa hình: khi generic có nhiều kiểu con hợp lệ

Đôi khi T không phải một kiểu cố định mà có thể là một trong nhiều subtype. Ví dụ một thông báo có thể là sự kiện tạo sách hoặc cập nhật sách. Trong trường hợp này, dùng một base type và mô tả các subtype bằng **oneOf** hoặc **anyOf**, thường kết hợp discriminator.

~~~java
@Schema(
    name = "BookEvent",
    oneOf = {
        BookCreatedEvent.class,
        BookUpdatedEvent.class
    },
    discriminatorProperty = "eventType"
)
public interface BookEvent {
}

@Schema(name = "BookCreatedEvent")
public record BookCreatedEvent(
    String eventType,
    UUID bookId,
    String title
) implements BookEvent {}

@Schema(name = "BookUpdatedEvent")
public record BookUpdatedEvent(
    String eventType,
    UUID bookId,
    String changedField
) implements BookEvent {}
~~~

Nếu wrapper là ApiEnvelope<BookEvent>, schema của data có thể tham chiếu tới BookEvent, trong đó oneOf liệt kê các dạng hợp lệ. Cách này mô tả rõ payload đa hình hơn việc dùng Object.

Hãy đảm bảo JSON runtime có đủ thông tin để client phân biệt subtype, thường là một discriminator property như eventType. Annotation OpenAPI chỉ mô tả hợp đồng; Jackson cũng cần được cấu hình để serialize/deserialize subtype tương ứng.

## 12. Những lỗi thường gặp và cách khắc phục

| Hiện tượng trong OpenAPI | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| data có schema object rỗng hoặc quá chung | Raw type, Object hoặc generic chưa resolve | Khai báo kiểu cụ thể trong method signature |
| data mất cấu trúc wrapper | Annotation response chỉ trỏ tới DTO bên trong | Mô tả đúng envelope hoặc concrete subclass |
| Wrapper xuất hiện như schema của Spring ResponseEntity | Nhầm transport wrapper với JSON body | Kiểm tra kiểu body bên trong ResponseEntity |
| Generic superclass không được specialization | Base class còn T chưa xác định trong ngữ cảnh controller | Override bằng kiểu cụ thể hoặc tạo concrete subclass |
| Tên component generic khó đọc hoặc thay đổi | Tên tự sinh phụ thuộc model converter | Dùng concrete subclass với @Schema(name = "...") |
| Request array chỉ hiện items kiểu Object | Generic request body không có type argument cụ thể | Dùng BulkRequest<CreateBookRequest> |
| @Schema(implementation=BookResponse.class) làm mất data/error | implementation thay thế schema envelope bằng DTO con | Chỉ định schema wrapper tương ứng |
| Schema oneOf không khớp JSON | Jackson không serialize discriminator hoặc subtype như tài liệu | Đồng bộ cấu hình Jackson và OpenAPI |
| Response runtime có wrapper nhưng tài liệu không có | Chữ ký method hoặc @ApiResponse mô tả sai | So sánh JSON thực tế với schema response |

## 13. Kiểm tra generic schema được springdoc sinh ra

Sau khi ứng dụng khởi động, lấy đặc tả tại **/v3/api-docs** hoặc endpoint YAML nếu đã bật. Đối với mỗi operation dùng generic, hãy kiểm tra:

1. Operation có đúng status code và media type không?
2. Schema response có giữ lớp bao dữ liệu của ứng dụng không?
3. Property data có trỏ tới kiểu cụ thể mong đợi không?
4. Nếu data là array, items có đúng schema của phần tử không?
5. Nếu generic lồng nhau, từng cấp có giữ đúng kiểu không?
6. Schema component có tên duy nhất và các $ref có hợp lệ không?
7. Request body generic có thể hiện đúng kiểu phần tử được nhận không?
8. Payload JSON runtime có khớp cấu trúc đã công bố không?

Có thể dùng jq để xem schema response:

~~~bash
curl -s http://localhost:8080/v3/api-docs | jq '.paths["/api/books/{bookId}"].get.responses["200"].content["application/json"].schema'
~~~

Sau đó mở component được tham chiếu:

~~~bash
curl -s http://localhost:8080/v3/api-docs | jq '.components.schemas'
~~~

Nếu schema bị inline, hãy kiểm tra trực tiếp các property trong response schema. Nếu schema dùng $ref, xác nhận đường dẫn tham chiếu trỏ tới component tồn tại.

### So sánh schema với JSON thực tế

Gọi endpoint bằng HTTP client hoặc integration test, lấy JSON thực tế rồi đối chiếu:

- success có phải boolean không?
- data có đúng object/array đã công bố không?
- error có đúng cấu trúc và có xuất hiện ở trường hợp lỗi không?
- Các property trong DTO có đúng tên sau khi Jackson serialize không?
- Status code và content type có khớp với response được mô tả không?

Đặc tả OpenAPI hợp lệ về cú pháp vẫn có thể sai về hợp đồng nếu wrapper hoặc generic argument bị mất. Cần kiểm tra cả cấu trúc JSON và schema, không chỉ xác nhận Swagger UI mở được.

## 14. Nguyên tắc thiết kế generic wrapper

- Dùng generic Wrapper<T> khi cấu trúc bao ngoài giống nhau nhưng kiểu dữ liệu bên trong thay đổi theo endpoint.
- Khai báo type argument cụ thể trong chữ ký controller, chẳng hạn ApiEnvelope<BookResponse>.
- Với generic lồng nhau, giữ đầy đủ từng cấp như ApiEnvelope<PageResponse<BookResponse>>.
- Tránh raw type, Object và wildcard không cần thiết ở ranh giới API công khai.
- Phân biệt ResponseEntity của Spring với wrapper JSON do ứng dụng định nghĩa.
- Dùng concrete subclass khi cần tên schema ổn định hoặc một kiểu response chuyên biệt.
- Dùng oneOf/anyOf và discriminator khi payload thực sự có nhiều subtype hợp lệ.
- Chỉ ghi đè schema bằng @Schema(implementation = ...) khi kiểu đó khớp JSON runtime.
- Giữ DTO request và response rõ ràng nếu hai hướng có cấu trúc khác nhau.
- Kiểm tra /v3/api-docs cùng payload thực tế sau mỗi thay đổi về generic hoặc wrapper.

## Kết luận

Generic giúp tái sử dụng wrapper và cấu trúc phân trang mà vẫn giữ kiểu dữ liệu cụ thể trong chữ ký Java. springdoc-openapi có thể phân tích generic metadata để tạo schema lồng nhau khi controller khai báo specialization rõ ràng. Type erasure khiến instance runtime không mang class riêng cho từng tham số kiểu, nhưng generic Signature trong khai báo class và method vẫn có thể được reflection đọc. Raw type, Object, wildcard hoặc type variable chưa resolve là những nguyên nhân phổ biến làm schema mất thông tin. Hãy khai báo kiểu cụ thể, phân biệt ResponseEntity với wrapper JSON, dùng concrete subclass hoặc annotation implementation đúng phạm vi khi cần, rồi đối chiếu OpenAPI JSON với payload thực tế.
