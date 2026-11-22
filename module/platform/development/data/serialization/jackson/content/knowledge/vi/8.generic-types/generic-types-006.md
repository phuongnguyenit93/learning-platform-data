# Ánh xạ kiểu phản hồi có tham số như trang kết quả

Trong các API Java, dữ liệu trả về thường được bọc trong những cấu trúc tổng quát. Một endpoint có thể trả về `ApiResponse<StudentDto>`, endpoint khác trả về `ApiResponse<OrderDto>`. Với API phân trang, kiểu dữ liệu còn lồng nhau, chẳng hạn `ApiResponse<PageResponse<StudentDto>>`, trong đó `PageResponse<T>` chứa danh sách phần tử kiểu `T` cùng thông tin trang.

Java hỗ trợ generic để mô tả những cấu trúc này ở thời điểm biên dịch. Nhưng khi chạy chương trình, Java sử dụng type erasure: phần lớn thông tin tham số kiểu không còn được giữ như một `Class` thông thường. Vì vậy, nếu chỉ truyền `PageResponse.class` cho Jackson, thư viện biết kiểu lớp ngoài nhưng không biết phần tử trong `content` phải là `StudentDto`, `OrderDto` hay một kiểu khác.

Để ánh xạ đúng kiểu phản hồi có tham số, Jackson cung cấp hai cơ chế quan trọng:

- `TypeReference<T>`: giữ thông tin kiểu tổng quát thông qua lớp con ẩn danh.
- `JavaType` và `TypeFactory`: xây dựng mô tả kiểu ở thời gian chạy, phù hợp khi kiểu phần tử chỉ được xác định động.

## 1. Hiểu cấu trúc phản hồi có tham số

Giả sử một API trả về danh sách học viên theo trang. JSON có thể có dạng:

```json
{
  "success": true,
  "message": "OK",
  "data": {
    "content": [
      {
        "id": 23,
        "name": "Lan"
      },
      {
        "id": 24,
        "name": "Minh"
      }
    ],
    "pageNumber": 0,
    "pageSize": 2,
    "totalElements": 51,
    "totalPages": 26
  }
}
```

Ở đây có hai lớp generic lồng nhau:

```text
ApiResponse<PageResponse<StudentDto>>
    |
    +-- success: boolean
    +-- message: String
    +-- data: PageResponse<StudentDto>
              |
              +-- content: List<StudentDto>
              +-- pageNumber: int
              +-- pageSize: int
              +-- totalElements: long
              +-- totalPages: int
```

`ApiResponse<T>` là envelope dùng chung cho nhiều loại dữ liệu. `PageResponse<T>` là cấu trúc trang có thể chứa `StudentDto`, `OrderDto`, `ProductDto` hoặc kiểu khác. Cả hai lớp đều không cần biết trước kiểu cụ thể của `T`.

Ví dụ mô hình Java:

```java
public class ApiResponse<T> {
    private boolean success;
    private String message;
    private T data;

    public ApiResponse() {
    }

    public boolean isSuccess() {
        return success;
    }

    public void setSuccess(boolean success) {
        this.success = success;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }
}
```

Lớp biểu diễn trang:

```java
import java.util.ArrayList;
import java.util.List;

public class PageResponse<T> {
    private List<T> content = new ArrayList<>();
    private int pageNumber;
    private int pageSize;
    private long totalElements;
    private int totalPages;

    public PageResponse() {
    }

    public List<T> getContent() {
        return content;
    }

    public void setContent(List<T> content) {
        this.content = content;
    }

    public int getPageNumber() {
        return pageNumber;
    }

    public void setPageNumber(int pageNumber) {
        this.pageNumber = pageNumber;
    }

    public int getPageSize() {
        return pageSize;
    }

    public void setPageSize(int pageSize) {
        this.pageSize = pageSize;
    }

    public long getTotalElements() {
        return totalElements;
    }

    public void setTotalElements(long totalElements) {
        this.totalElements = totalElements;
    }

    public int getTotalPages() {
        return totalPages;
    }

    public void setTotalPages(int totalPages) {
        this.totalPages = totalPages;
    }
}
```

Kiểu phần tử có thể là DTO thông thường:

```java
public class StudentDto {
    private long id;
    private String name;

    public StudentDto() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Khi khai báo trong code nghiệp vụ, kiểu đầy đủ có thể viết như sau:

```java
ApiResponse<PageResponse<StudentDto>> response;
```

Khai báo này giúp compiler kiểm tra kiểu khi chương trình sử dụng `response`. Nhưng để Jackson tạo đúng kiểu lồng nhau từ JSON, cần cung cấp thông tin generic ở thời điểm đọc.

## 2. Vì sao PageResponse.class không đủ?

Java generic được triển khai chủ yếu bằng type erasure. Ví dụ:

```java
PageResponse<StudentDto> studentPage;
PageResponse<OrderDto> orderPage;
```

Ở thời gian chạy, cả hai đều có class runtime là `PageResponse.class`. Tham số `StudentDto` và `OrderDto` không được biểu diễn bằng hai đối tượng `Class` riêng biệt.

Nếu đọc JSON như sau:

```java
PageResponse page = mapper.readValue(json, PageResponse.class);
```

Jackson chỉ nhận được kiểu lớp thô (raw type). Nó biết trường `content` là một danh sách, nhưng không biết phần tử của danh sách phải được ánh xạ thành `StudentDto`. Với JSON object, các phần tử có thể được tạo thành `LinkedHashMap`; giá trị số và chuỗi vẫn là các kiểu Java cơ bản tương ứng.

Ví dụ lỗi thường gặp:

```java
PageResponse page = mapper.readValue(json, PageResponse.class);

Object first = page.getContent().get(0);
System.out.println(first.getClass());
```

Kết quả có thể là `LinkedHashMap`, không phải `StudentDto`. Nếu code ép kiểu trực tiếp:

```java
StudentDto student = (StudentDto) page.getContent().get(0);
```

ứng dụng có thể gặp `ClassCastException`.

Vấn đề nằm ở chỗ kiểu generic đã bị mất khi chỉ truyền `PageResponse.class`. Cần truyền một mô tả kiểu đầy đủ như `PageResponse<StudentDto>` cho Jackson.

## 3. Dùng TypeReference cho kiểu generic đã biết

`TypeReference<T>` là cách thuận tiện khi kiểu đích được biết ngay tại vị trí gọi. Jackson dùng thông tin generic trong lớp con ẩn danh để lấy kiểu tổng quát.

Đọc một trang học viên:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

TypeReference<PageResponse<StudentDto>> pageType =
    new TypeReference<PageResponse<StudentDto>>() {};

PageResponse<StudentDto> page = mapper.readValue(json, pageType);

StudentDto firstStudent = page.getContent().get(0);
System.out.println(firstStudent.getName());
```

Điểm quan trọng là `TypeReference` phải được tạo với kiểu cụ thể đầy đủ. Biểu thức:

```java
new TypeReference<PageResponse<StudentDto>>() {}
```

giữ được thông tin `StudentDto` trong kiểu generic mà lớp con ẩn danh khai báo.

### 3.1. Đọc envelope chứa trang kết quả

Nếu JSON có thêm lớp `ApiResponse<T>`, cần mô tả cả hai tầng generic:

```java
TypeReference<ApiResponse<PageResponse<StudentDto>>> responseType =
    new TypeReference<ApiResponse<PageResponse<StudentDto>>>() {};

ApiResponse<PageResponse<StudentDto>> response =
    mapper.readValue(json, responseType);

PageResponse<StudentDto> page = response.getData();
StudentDto firstStudent = page.getContent().get(0);
```

Jackson biết `data` là `PageResponse<StudentDto>`, rồi biết `content` là `List<StudentDto>`. Mỗi phần tử trong danh sách được ánh xạ thành DTO tương ứng.

`TypeReference` đặc biệt hữu ích cho những kiểu có cấu trúc lồng nhau như:

```java
new TypeReference<ApiResponse<List<StudentDto>>>() {};
new TypeReference<Map<String, StudentDto>>() {};
new TypeReference<Map<String, List<OrderDto>>>() {};
new TypeReference<PageResponse<Map<String, Object>>>() {};
```

Không cần tạo lớp wrapper riêng chỉ để giữ một tham số generic nếu kiểu đích đã có thể mô tả bằng `TypeReference`.

## 4. Dùng JavaType và TypeFactory khi kiểu được xác định lúc chạy

`TypeReference` phù hợp khi code biết kiểu cụ thể tại thời điểm viết. Nhưng đôi khi kiểu phần tử được lựa chọn theo cấu hình hoặc theo loại endpoint ở runtime. Trong trường hợp đó, Jackson cung cấp `JavaType` và `TypeFactory`.

`JavaType` là mô tả kiểu mà Jackson hiểu được, bao gồm lớp raw và các tham số generic. `TypeFactory` xây dựng mô tả này từ `Class`, `JavaType` hoặc các kiểu thành phần khác.

Ví dụ xây dựng `PageResponse<StudentDto>`:

```java
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.type.TypeFactory;

ObjectMapper mapper = new ObjectMapper();
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType pageType = typeFactory.constructParametricType(
    PageResponse.class,
    StudentDto.class
);

PageResponse<StudentDto> page = mapper.readValue(json, pageType);
```

`constructParametricType` nhận lớp generic và kiểu của các tham số. Với `PageResponse<T>`, có một tham số nên truyền `StudentDto.class`.

### 4.1. Xây dựng kiểu generic lồng nhau

Với `ApiResponse<PageResponse<StudentDto>>`, cần xây dựng kiểu trong cùng trước, rồi dùng nó làm tham số của lớp ngoài:

```java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType pageType = typeFactory.constructParametricType(
    PageResponse.class,
    StudentDto.class
);

JavaType responseType = typeFactory.constructParametricType(
    ApiResponse.class,
    pageType
);

ApiResponse<PageResponse<StudentDto>> response =
    mapper.readValue(json, responseType);
```

Có thể hình dung quá trình tạo kiểu:

```text
StudentDto.class
      |
      v
PageResponse<StudentDto>
      |
      v
ApiResponse<PageResponse<StudentDto>>
```

Việc xây dựng từ trong ra ngoài giúp từng lớp generic nhận đúng kiểu tham số.

### 4.2. Dùng JavaType cho collection

Jackson cũng có các phương thức tiện ích để tạo kiểu collection:

```java
JavaType studentListType = typeFactory.constructCollectionType(
    List.class,
    StudentDto.class
);

List<StudentDto> students = mapper.readValue(json, studentListType);
```

Với map:

```java
JavaType studentMapType = typeFactory.constructMapType(
    Map.class,
    String.class,
    StudentDto.class
);

Map<String, StudentDto> studentsByCode =
    mapper.readValue(json, studentMapType);
```

Với cấu trúc lồng nhau, có thể truyền `JavaType` đã tạo làm tham số của một kiểu khác:

```java
JavaType studentMapType = typeFactory.constructMapType(
    Map.class,
    String.class,
    StudentDto.class
);

JavaType listOfMapsType = typeFactory.constructCollectionType(
    List.class,
    studentMapType
);

List<Map<String, StudentDto>> result =
    mapper.readValue(json, listOfMapsType);
```

Các kiểu như `Map<String, List<StudentDto>>` hoặc `ApiResponse<List<OrderDto>>` cũng có thể được xây dựng bằng cách ghép các `JavaType` theo từng tầng.

## 5. Chọn TypeReference hay JavaType?

Hai cơ chế đều cung cấp thông tin kiểu generic cho Jackson, nhưng phù hợp với cách tổ chức code khác nhau.

| Tiêu chí | `TypeReference<T>` | `JavaType` / `TypeFactory` |
|---|---|---|
| Kiểu đích đã biết tại vị trí gọi | Rất thuận tiện | Dùng được nhưng dài hơn |
| Kiểu phần tử xác định ở runtime | Không thuận tiện nếu chỉ có `Class<T>` | Phù hợp |
| Kiểu generic lồng nhau | Dễ đọc bằng cú pháp Java | Xây dựng từng tầng rõ ràng |
| API nhận tham số kiểu động | Cần truyền một `TypeReference` cụ thể | Có thể truyền trực tiếp `JavaType` |
| Tái sử dụng kiểu đã xây dựng | Có thể giữ đối tượng reference | Có thể giữ và tái sử dụng `JavaType` |

Nếu code biết rõ `ApiResponse<PageResponse<StudentDto>>`, `TypeReference` thường dễ đọc nhất. Nếu một registry chọn `StudentDto`, `OrderDto` hoặc `ProductDto` từ cấu hình runtime, `JavaType` giúp xây dựng kiểu đích mà không cần tạo lớp con ẩn danh cho từng trường hợp.

## 6. Type erasure trong phương thức generic

Một lỗi tinh vi thường xuất hiện khi viết helper generic. Ví dụ:

```java
public <T> PageResponse<T> readPage(
        String json,
        ObjectMapper mapper) throws JsonProcessingException {

    return mapper.readValue(
        json,
        new TypeReference<PageResponse<T>>() {}
    );
}
```

Đoạn code trông có vẻ hợp lý, nhưng `T` ở đây là tham số kiểu của phương thức và đã bị type erasure khi chạy. Lớp con ẩn danh không thể tự biết `T` thực tế là `StudentDto` hay `OrderDto`. Kết quả có thể vẫn là kiểu chưa xác định hoặc Jackson ánh xạ phần tử thành cấu trúc map chung, tùy tình huống.

Một helper generic cần nhận thông tin kiểu từ caller. Có thể truyền `Class<T>` nếu phần tử là kiểu không generic:

```java
public static <T> PageResponse<T> readPage(
        String json,
        Class<T> itemClass,
        ObjectMapper mapper) throws JsonProcessingException {

    JavaType pageType = mapper.getTypeFactory()
        .constructParametricType(PageResponse.class, itemClass);

    return mapper.readValue(json, pageType);
}
```

Sử dụng:

```java
PageResponse<StudentDto> students =
    readPage(json, StudentDto.class, mapper);

PageResponse<OrderDto> orders =
    readPage(json, OrderDto.class, mapper);
```

Nếu kiểu phần tử cũng là generic, `Class<T>` không đủ. Hãy nhận `JavaType`:

```java
public static <T> PageResponse<T> readPage(
        String json,
        JavaType itemType,
        ObjectMapper mapper) throws JsonProcessingException {

    JavaType pageType = mapper.getTypeFactory()
        .constructParametricType(PageResponse.class, itemType);

    return mapper.readValue(json, pageType);
}
```

Caller có thể xây dựng kiểu phần tử trước:

```java
JavaType itemType = mapper.getTypeFactory().constructParametricType(
    KeyValueDto.class,
    String.class,
    Integer.class
);

PageResponse<KeyValueDto<String, Integer>> page =
    readPage(json, itemType, mapper);
```

Một lựa chọn khác là nhận `TypeReference<T>` do caller tạo:

```java
public static <T> T decode(
        String json,
        TypeReference<T> targetType,
        ObjectMapper mapper) throws JsonProcessingException {
    return mapper.readValue(json, targetType);
}
```

Gọi helper với kiểu đầy đủ tại nơi biết kiểu:

```java
ApiResponse<PageResponse<StudentDto>> response = decode(
    json,
    new TypeReference<ApiResponse<PageResponse<StudentDto>>>() {},
    mapper
);
```

Điểm mấu chốt: generic helper không thể tự khôi phục thông tin tham số kiểu đã bị xóa. Caller phải truyền một type token hoặc `JavaType` mang đủ thông tin.

## 7. Dùng ObjectReader với kiểu phản hồi có tham số

Khi cùng một loại phản hồi được đọc nhiều lần, có thể tạo `ObjectReader` với `JavaType` đã xây dựng:

```java
JavaType responseType = mapper.getTypeFactory()
    .constructParametricType(
        ApiResponse.class,
        mapper.getTypeFactory().constructParametricType(
            PageResponse.class,
            StudentDto.class
        )
    );

ObjectReader studentPageReader = mapper.readerFor(responseType);

ApiResponse<PageResponse<StudentDto>> response =
    studentPageReader.readValue(json);
```

Reader giữ kiểu đích và có thể được tái sử dụng. Cách này phù hợp với adapter chuyên xử lý một hợp đồng đối tác hoặc một endpoint có cấu trúc ổn định.

Nếu mỗi request chọn một kiểu phần tử khác nhau, hãy tạo reader từ `JavaType` tương ứng. Không thay đổi mapper dùng chung để đáp ứng từng request.

## 8. Ánh xạ kiểu phản hồi phân trang

Một page response thường chứa hai nhóm dữ liệu:

1. **Nội dung trang:** danh sách các phần tử có kiểu `T`.
2. **Metadata phân trang:** số trang hiện tại, kích thước trang, tổng số bản ghi và tổng số trang.

Ví dụ:

```java
public class PageResponse<T> {
    private List<T> content;
    private int pageNumber;
    private int pageSize;
    private long totalElements;
    private int totalPages;

    // Constructor, getter và setter.
}
```

Khi JSON có `content` là array object, Jackson cần biết `T` để tạo đúng kiểu từng phần tử. Metadata là kiểu cụ thể (`int`, `long`) nên không có vấn đề generic.

### 8.1. Phân biệt trang rỗng và trang cuối

Một trang hợp lệ có thể không có phần tử:

```json
{
  "content": [],
  "pageNumber": 5,
  "pageSize": 20,
  "totalElements": 100,
  "totalPages": 5
}
```

Khi ánh xạ, `content` vẫn là `List<StudentDto>` nhưng rỗng. Không nên suy luận kiểu phần tử từ phần tử đầu tiên vì trang rỗng không có phần tử để suy ra. Chính `JavaType` hoặc `TypeReference` cung cấp thông tin kiểu, kể cả khi array rỗng.

Hợp đồng phân trang cần quy định rõ:

- `pageNumber` bắt đầu từ 0 hay 1.
- `pageSize` là số phần tử tối đa hay số phần tử thực tế.
- `totalElements` là tổng số bản ghi phù hợp bộ lọc hay tổng số bản ghi toàn hệ thống.
- `totalPages` được tính thế nào khi không có phần tử hoặc page size bằng 0.
- Có trả về thông tin sắp xếp, filter, next/previous link hay cursor không.

Jackson chỉ ánh xạ các giá trị vào field. Nó không tự xác minh rằng `totalPages` phù hợp với `totalElements` và `pageSize`, hoặc `content.size()` không vượt giới hạn trang. Các quy tắc nhất quán này thuộc validation của ứng dụng.

### 8.2. Không nhất thiết deserialize trực tiếp Spring Data Page

Trong Spring Data, `Page<T>` là interface mang hành vi và metadata phân trang. Nó không đơn thuần là một DTO JSON có constructor rõ ràng. Cố deserialize trực tiếp một interface hoặc implementation nội bộ như `PageImpl` có thể phụ thuộc vào chi tiết constructor, phiên bản hoặc module hỗ trợ.

Đối với API công khai, thường nên tạo `PageResponse<T>` riêng với các trường ổn định. Ở chiều trả dữ liệu, chuyển từ `Page<T>` của Spring Data sang DTO response; ở chiều nhận, dùng DTO page tương ứng nếu giao thức thực sự yêu cầu. Cách này tránh để hợp đồng JSON phụ thuộc cấu trúc nội bộ của framework persistence.

## 9. Kiểu generic lồng nhiều tầng

Các API thực tế thường bọc dữ liệu qua nhiều lớp:

```java
ApiResponse<PageResponse<StudentDto>>
ApiResponse<List<OrderDto>>
ApiResponse<Map<String, List<ProductDto>>>
PageResponse<Map<String, Object>>
```

Với `TypeReference`, có thể mô tả trực tiếp:

```java
TypeReference<ApiResponse<Map<String, List<ProductDto>>>> type =
    new TypeReference<ApiResponse<Map<String, List<ProductDto>>>>() {};

ApiResponse<Map<String, List<ProductDto>>> response =
    mapper.readValue(json, type);
```

Với `JavaType`, xây dựng từ trong ra ngoài:

```java
TypeFactory types = mapper.getTypeFactory();

JavaType productListType = types.constructCollectionType(
    List.class,
    ProductDto.class
);

JavaType productMapType = types.constructMapType(
    Map.class,
    String.class,
    productListType
);

JavaType responseType = types.constructParametricType(
    ApiResponse.class,
    productMapType
);

ApiResponse<Map<String, List<ProductDto>>> response =
    mapper.readValue(json, responseType);
```

Xây dựng kiểu theo từng tầng giúp tránh nhầm thứ tự tham số generic và dễ kiểm tra khi cấu trúc trở nên phức tạp.

## 10. Serialize kiểu generic

Khi serialize một đối tượng đã được tạo với dữ liệu cụ thể, Jackson thường có thể nhận diện kiểu runtime của các phần tử trong collection. Ví dụ, `PageResponse<StudentDto>` có `content` chứa các instance `StudentDto`, vì vậy mapper có thể ghi các thuộc tính của chúng.

```java
PageResponse<StudentDto> page = new PageResponse<>();
page.setContent(List.of(student1, student2));

String json = mapper.writeValueAsString(page);
```

Tuy nhiên, kiểu generic vẫn có ý nghĩa trong một số trường hợp: collection rỗng không cung cấp phần tử để suy ra kiểu; thuộc tính khai báo qua generic base class có thể cần thông tin kiểu tĩnh; custom serializer hoặc polymorphic type handling có thể phụ thuộc kiểu đích. Khi cần xác định rõ kiểu đầu ra, tạo `JavaType` và writer:

```java
JavaType pageType = mapper.getTypeFactory()
    .constructParametricType(PageResponse.class, StudentDto.class);

ObjectWriter pageWriter = mapper.writerFor(pageType);
String json = pageWriter.writeValueAsString(page);
```

Về mặt JSON, tham số `T` không được ghi như một phần tử generic đặc biệt. JSON chỉ chứa object, array và các giá trị. `JavaType` giúp Jackson chọn cách serialize theo kiểu Java đã khai báo; nó không tự thêm tên lớp hoặc metadata kiểu vào JSON nếu không có cấu hình polymorphic tương ứng.

## 11. Xử lý trường hợp kiểu phần tử phức tạp

Nếu phần tử trang không phải một DTO đơn giản mà là kiểu generic khác, hãy xây dựng kiểu đầy đủ.

Ví dụ `PageResponse<KeyValueDto<String, Integer>>`:

```java
public class KeyValueDto<K, V> {
    private K key;
    private V value;

    public KeyValueDto() {
    }

    public K getKey() {
        return key;
    }

    public void setKey(K key) {
        this.key = key;
    }

    public V getValue() {
        return value;
    }

    public void setValue(V value) {
        this.value = value;
    }
}
```

Xây dựng kiểu phần tử rồi dùng làm tham số của page:

```java
TypeFactory types = mapper.getTypeFactory();

JavaType keyValueType = types.constructParametricType(
    KeyValueDto.class,
    String.class,
    Integer.class
);

JavaType pageType = types.constructParametricType(
    PageResponse.class,
    keyValueType
);

PageResponse<KeyValueDto<String, Integer>> page =
    mapper.readValue(json, pageType);
```

Nếu `T` là `List<Map<String, ProductDto>>`, có thể tạo `JavaType` cho map, sau đó collection, rồi page. Mỗi lớp generic cần nhận đủ kiểu tham số của nó.

## 12. Kiểm tra kiểu và dữ liệu sau khi ánh xạ

Truyền đúng generic type giúp Jackson tạo đúng loại đối tượng, nhưng không tự bảo đảm dữ liệu hợp lệ về nghiệp vụ.

Ví dụ, JSON có thể chứa:

```json
{
  "content": [
    {"id": 23, "name": "Lan"}
  ],
  "pageNumber": -1,
  "pageSize": 0,
  "totalElements": -10,
  "totalPages": 999
}
```

Jackson có thể ánh xạ những giá trị số này vào các field tương ứng vì chúng đúng kiểu `int` hoặc `long`. Nhưng metadata phân trang không hợp lệ. Ứng dụng cần kiểm tra:

- `pageNumber` không âm nếu API dùng đánh số từ 0.
- `pageSize` nằm trong giới hạn được phép và lớn hơn 0 theo hợp đồng.
- `totalElements` không âm.
- `totalPages` phù hợp với tổng số phần tử và quy tắc tính trang.
- `content` không null nếu hợp đồng yêu cầu danh sách luôn tồn tại.
- Số phần tử thực tế không vượt `pageSize` nếu đó là giới hạn của API.

Có thể dùng Bean Validation hoặc hàm kiểm tra chuyên biệt. Đừng đặt các quy tắc này vào custom deserializer chỉ vì dữ liệu được đọc bằng Jackson; chúng là quy tắc của hợp đồng ứng dụng và có thể cần áp dụng cho dữ liệu đến từ nhiều nguồn.

## 13. Những lỗi thường gặp khi ánh xạ kiểu phản hồi generic

### 13.1. Dùng raw type

```java
PageResponse page = mapper.readValue(json, PageResponse.class);
```

Jackson không có thông tin `T`, nên phần tử object có thể trở thành `LinkedHashMap`. Hãy dùng `TypeReference<PageResponse<StudentDto>>` hoặc `JavaType`.

### 13.2. Dùng `List.class` rồi ép kiểu

```java
List<StudentDto> students = mapper.readValue(json, List.class);
```

Kiểu trả về thực tế chỉ là danh sách object tổng quát. Generic type ở vế trái không truyền ngược thông tin cho Jackson. Hãy cung cấp `TypeReference<List<StudentDto>>` hoặc `constructCollectionType`.

### 13.3. Tạo TypeReference<T> bên trong generic helper

```java
public <T> T decode(String json) throws IOException {
    return mapper.readValue(json, new TypeReference<T>() {});
}
```

`T` đã bị type erasure; helper không thể tự biết kiểu cụ thể. Nhận `TypeReference<T>`, `JavaType` hoặc `Class<T>` từ caller.

### 13.4. Chỉ truyền Class<T> khi T cũng là generic

`Class<PageResponse>` không thể biểu diễn `PageResponse<StudentDto>`. `Class<T>` chỉ đủ khi kiểu đích không cần tham số generic. Với kiểu lồng nhau, dùng `JavaType` hoặc `TypeReference`.

### 13.5. Nhầm lẫn giữa JSON hợp lệ và page hợp lệ

Jackson có thể parse được `pageSize: 0` hoặc `pageNumber: -1`. Parse thành công chỉ cho biết dữ liệu có thể ánh xạ về kiểu Java; ứng dụng vẫn phải kiểm tra ràng buộc phân trang.

## 14. Ví dụ helper tổng quát cho page response

Nếu nhiều adapter cần đọc trang có kiểu phần tử khác nhau, có thể tạo helper nhận `Class<T>`:

```java
public final class PageResponseReader {
    private final ObjectMapper mapper;

    public PageResponseReader(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public <T> PageResponse<T> read(
            String json,
            Class<T> itemClass) throws JsonProcessingException {

        JavaType pageType = mapper.getTypeFactory()
            .constructParametricType(PageResponse.class, itemClass);

        return mapper.readValue(json, pageType);
    }
}
```

Sử dụng:

```java
PageResponse<StudentDto> studentPage =
    pageReader.read(studentJson, StudentDto.class);

PageResponse<OrderDto> orderPage =
    pageReader.read(orderJson, OrderDto.class);
```

Nếu kiểu phần tử có tham số generic, cung cấp `JavaType` thay vì `Class<T>`:

```java
public <T> PageResponse<T> read(
        String json,
        JavaType itemType) throws JsonProcessingException {

    JavaType pageType = mapper.getTypeFactory()
        .constructParametricType(PageResponse.class, itemType);

    return mapper.readValue(json, pageType);
}
```

Không cần viết helper tổng quát nếu chỉ có một endpoint. `TypeReference` trực tiếp tại vị trí gọi có thể dễ đọc hơn. Chỉ tạo abstraction khi nhiều luồng thực sự chia sẻ cùng cách xử lý.

## 15. Lựa chọn giữa TypeReference, JavaType và DTO cụ thể

| Tình huống | Cách tiếp cận |
|---|---|
| Một endpoint luôn trả `PageResponse<StudentDto>` | `TypeReference<PageResponse<StudentDto>>` |
| Một endpoint luôn trả `ApiResponse<PageResponse<StudentDto>>` | `TypeReference<ApiResponse<PageResponse<StudentDto>>>` |
| Kiểu phần tử chọn từ cấu hình runtime | `TypeFactory` xây dựng `JavaType` |
| Helper generic nhận kiểu phần tử không generic | Nhận `Class<T>` rồi tạo `JavaType` |
| Helper generic nhận kiểu phần tử có generic | Nhận `JavaType` hoặc `TypeReference<T>` từ caller |
| Nhiều endpoint có cấu trúc khác nhau nhưng ít dùng chung | Khai báo kiểu cụ thể tại từng adapter |
| API cần hợp đồng ổn định, metadata trang rõ ràng | Dùng `PageResponse<T>` DTO riêng |

Nếu ứng dụng dùng Spring Data, không nhất thiết deserialize trực tiếp vào `Page<T>` hoặc implementation nội bộ của framework. `Page<T>` là abstraction có hành vi và metadata; nó không đơn thuần là một DTO có constructor ổn định. Với API công khai, thường nên chuyển sang `PageResponse<T>` do ứng dụng định nghĩa để tránh phụ thuộc cấu trúc serialization của phiên bản Spring Data.

## 16. Tổng kết

Để Jackson ánh xạ đúng kiểu phản hồi có tham số, cần cung cấp đầy đủ thông tin generic tại thời điểm đọc. `PageResponse.class` hoặc `List.class` không đủ để chỉ ra kiểu phần tử vì Java type erasure. Khi kiểu đích đã biết, `TypeReference<T>` là cách ngắn gọn và dễ đọc. Khi kiểu được chọn động hoặc cần xây dựng nhiều tầng generic, `JavaType` và `TypeFactory` cho phép ghép kiểu từ trong ra ngoài.

Với phản hồi phân trang, hãy mô tả rõ `content` cùng metadata như `pageNumber`, `pageSize`, `totalElements` và `totalPages`. Truyền đúng kiểu giúp Jackson tạo DTO đúng, nhưng ứng dụng vẫn cần xác thực tính hợp lệ và nhất quán của metadata. Khi thiết kế helper generic, luôn nhận type token hoặc `JavaType` từ caller thay vì mong đợi phương thức tự khôi phục tham số kiểu đã bị xóa. Điều đó giúp quá trình đọc JSON có kiểu rõ ràng, an toàn và dễ bảo trì.
