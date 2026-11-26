# Chuyển đổi kiểu, nhiều giá trị và điều kiện không hợp lệ

## Mục tiêu và phạm vi

Một bộ lọc web thường bắt đầu bằng các chuỗi như `state=ACTIVE`, `minPrice=10.00` hoặc nhiều lần xuất hiện của cùng một tham số. Repository không nên phải tự đoán các chuỗi này có nghĩa gì.

Bài học thuộc chương **Bộ lọc và payload web** của module **SPRING_DATA_COMMONS**. Trọng tâm là chuyển dữ liệu HTTP thành điều kiện có kiểu, xác định ngữ nghĩa nhiều giá trị và từ chối điều kiện không hợp lệ trước khi gọi tầng dữ liệu.

Các abstraction của Spring Data như repository, Querydsl integration và Query by Example có thể tiếp nhận điều kiện theo những cách khác nhau. Khả năng thực thi vẫn phụ thuộc từng module store; Commons không cung cấp một ngôn ngữ truy vấn HTTP tự động áp dụng giống nhau cho mọi kho dữ liệu.

Sau bài học, bạn có thể:

1. Phân biệt lỗi cú pháp, lỗi chuyển đổi kiểu và lỗi quan hệ giữa các điều kiện.
2. Quy định cách hiểu tham số lặp, scalar và collection.
3. Xử lý thiếu, rỗng, null và giá trị không được hỗ trợ.
4. Tạo một bộ lọc có kiểu cùng response lỗi có cấu trúc.
5. Áp dụng đúng cơ chế binding của MVC, payload JSON và Querydsl.

Ví dụ chính dùng Java 17 trở lên, Spring MVC và `ProblemDetail` của Spring Framework 6 trở lên. Các đoạn mã được hiểu là những đơn vị mã nguồn riêng trong cùng package khi thực hành.

## 1. Ba giai đoạn cần phân biệt

~~~mermaid
flowchart LR
    A["Chuỗi query hoặc payload"] --> B["Kiểm tra tên và số giá trị"]
    B --> C["Chuyển đổi kiểu"]
    C --> D["Kiểm tra quan hệ điều kiện"]
    D --> E["Bộ lọc có kiểu"]
    E --> F["Thêm phạm vi được phép"]
    F --> G["Truy vấn theo module store"]
~~~

Ví dụ:

| Đầu vào | Vấn đề |
|---|---|
| `minPrice=ten` | Không chuyển được thành giá |
| `state=UNKNOWN` | Không thuộc tập trạng thái được hỗ trợ |
| `minPrice=100&maxPrice=10` | Hai giá đều có kiểu hợp lệ nhưng khoảng bị đảo |
| `available=true&available=false` | Scalar nhận nhiều giá trị |
| `state=ACTIVE&state=PAUSED` | Hợp lệ nếu hợp đồng quy định nhiều trạng thái |
| `supplierCost=0` | Tên điều kiện không nằm trong hợp đồng public |
| `createdFrom=2026-01-01` | Thiếu thông tin thời điểm theo hợp đồng có offset |

Conversion chỉ trả lời “chuỗi có chuyển thành kiểu đích không?”. Validation còn phải trả lời “giá trị và tổ hợp điều kiện đó có hợp lệ với endpoint này không?”.

Một query hợp lệ về kiểu cũng không chứng minh người gọi được đọc mọi dữ liệu phù hợp. Phạm vi tenant hoặc quyền truy cập cần được áp dụng riêng.

## 2. Định nghĩa hợp đồng nhiều giá trị trước khi binding

Ta thiết kế endpoint minh họa:

~~~http
GET /products/search?state=ACTIVE&state=PAUSED&minPrice=10.00&maxPrice=100.00&available=true
~~~

Các tham số được phép:

| Tên | Số giá trị | Kiểu và quy tắc |
|---|---|---|
| `id` | Từ 1 đến 50 nếu xuất hiện | UUID dạng chuẩn, nhiều ID mang nghĩa IN |
| `state` | Từ 1 đến 50 nếu xuất hiện | `ACTIVE`, `PAUSED` hoặc `ARCHIVED`, nhiều giá trị mang nghĩa IN |
| `minPrice` | Tối đa 1 | Giá không âm, tối đa 12 chữ số phần nguyên và 2 chữ số phần lẻ |
| `maxPrice` | Tối đa 1 | Cùng quy tắc với minPrice |
| `createdFrom` | Tối đa 1 | Thời điểm ISO-8601 có offset, cận dưới bao gồm |
| `createdBefore` | Tối đa 1 | Thời điểm ISO-8601 có offset, cận trên không bao gồm |
| `available` | Tối đa 1 | Chỉ nhận `true` hoặc `false` viết thường |

Đây là chính sách của ví dụ, không phải mặc định chung của Spring MVC.

Những quy ước bổ sung:

- Không xuất hiện tham số nghĩa là không thêm điều kiện client tương ứng.
- Nếu tham số xuất hiện nhưng không có giá trị hoặc chỉ có khoảng trắng, request không hợp lệ.
- Các giá trị được bỏ khoảng trắng đầu/cuối trước khi chuyển đổi.
- Một giá trị sau giải mã dài hơn 128 ký tự bị từ chối trong ví dụ.
- Scalar lặp bị từ chối, kể cả các giá trị giống nhau.
- Phần tử lặp hợp lệ trong collection được loại trùng.
- Nếu một phần tử sai, toàn bộ request bị từ chối; không bỏ phần tử đó rồi truy vấn phần còn lại.
- Tham số không được hỗ trợ bị từ chối.

### IN trong một trường, AND giữa các trường

Request:

~~~http
GET /products/search?state=ACTIVE&state=PAUSED&available=true
~~~

được hiểu là:

~~~text
(state = ACTIVE OR state = PAUSED)
AND available = true
AND các điều kiện phạm vi bắt buộc của server
~~~

Nó không có nghĩa một sản phẩm phải có đồng thời hai trạng thái.

Nếu `state` là một collection property trên domain, ý nghĩa “chứa một”, “chứa tất cả” hoặc “giao không rỗng” lại là những lựa chọn khác. Không suy ra toán tử chỉ từ việc URL có nhiều giá trị.

### Không tự coi dấu phẩy là dấu phân cách

Hợp đồng ví dụ dùng tham số lặp:

~~~http
?state=ACTIVE&state=PAUSED
~~~

Nó không chấp nhận `state=ACTIVE,PAUSED` như hai trạng thái. Nếu muốn hỗ trợ CSV, phải định nghĩa cú pháp, escaping và giới hạn riêng.

Không dùng `Map<String, String>` nếu cần giữ mọi giá trị của một tên tham số. `MultiValueMap<String, String>` giữ được danh sách giá trị, thuận tiện cho việc kiểm tra cardinality.

Spring MVC hỗ trợ đọc nhiều giá trị và map tham số như mô tả trong [RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html).

## 3. Thiếu, rỗng, false và null là những trạng thái khác nhau

| Đầu vào | Ý nghĩa trong ví dụ |
|---|---|
| Không có `available` | Không thêm điều kiện availability |
| `available=false` | Chỉ lấy dữ liệu thỏa availability bằng false |
| `available=` | Lỗi giá trị rỗng |
| `available=null` | Chuỗi “null”, không phải Java null; không hợp lệ |
| Không có `state` | Không thêm điều kiện state từ client |
| `state=` | Lỗi phần tử rỗng |
| `state=ACTIVE&state=` | Toàn bộ request không hợp lệ |

Đây là lý do bộ lọc tùy chọn thường dùng wrapper `Boolean` thay vì primitive `boolean`. Null có thể biểu diễn “không thêm điều kiện”, còn false vẫn là một điều kiện thực.

Không dùng:

~~~java
Boolean.parseBoolean(rawValue)
~~~

như một phép kiểm tra boolean nghiêm ngặt. API này trả false cho nhiều chuỗi không phải true, nên một lỗi nhập liệu có thể bị biến thành điều kiện false. Xem [Boolean.parseBoolean](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Boolean.html#parseBoolean(java.lang.String)).

Nếu API hỗ trợ lọc bản ghi có một property bằng null, nên có toán tử hoặc tham số rõ ràng, chẳng hạn `hasDescription=false`. Đừng tự diễn giải chuỗi `"null"` thành toán tử null cho mọi trường.

### Không “sửa hộ” điều kiện sai thành truy vấn rộng hơn

Nếu `state=UNKNOWN` bị bỏ qua, request có thể trở thành “không lọc state”. Điều đó khác hẳn ý định của client.

Tương tự, đổi giá không hợp lệ thành 0 hoặc khoảng thời gian sai thành không có khoảng có thể tạo ra tập kết quả ngoài mong đợi. Chỉ dùng giá trị mặc định khi hợp đồng thực sự quy định như vậy.

## 4. Chuyển đổi có kiểu bằng ConversionService

Spring MVC có thể chuyển đổi các tham số trực tiếp sang kiểu đích, ví dụ:

~~~java
public Object find(
    @RequestParam("minPrice") BigDecimal minPrice
) {
    // Chữ ký minh họa, chưa phải implementation của endpoint.
}
~~~

Tuy nhiên, khi cần kiểm soát cả scalar lặp, tên lạ và định dạng nghiêm ngặt, ta có thể đọc các giá trị thô rồi chuyển đổi có chủ đích.

`ConversionService` là API chuyển đổi kiểu của Spring. `Converter<S, T>` cho phép khai báo một quy tắc có kiểu. Converter phải an toàn khi được tái sử dụng giữa các request. Xem [Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html).

Trong ví dụ, ta tạo conversion service riêng cho bộ lọc này:

~~~java
public enum ProductState {
    ACTIVE,
    PAUSED,
    ARCHIVED
}
~~~

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.UUID;

import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ProductFilterConversions {

    private ProductFilterConversions() {
    }

    public static ConversionService create() {
        DefaultConversionService service =
            new DefaultConversionService();

        service.addConverter(
            String.class,
            ProductState.class,
            ProductState::valueOf
        );

        service.addConverter(
            String.class,
            Boolean.class,
            value -> switch (value) {
                case "true" -> Boolean.TRUE;
                case "false" -> Boolean.FALSE;
                default -> throw new IllegalArgumentException(
                    "Expected true or false"
                );
            }
        );

        service.addConverter(
            String.class,
            BigDecimal.class,
            value -> {
                if (!value.matches(
                    "[0-9]{1,12}(\\.[0-9]{1,2})?"
                )) {
                    throw new IllegalArgumentException(
                        "Invalid price format"
                    );
                }
                return new BigDecimal(value);
            }
        );

        service.addConverter(
            String.class,
            Instant.class,
            value -> OffsetDateTime.parse(
                value,
                DateTimeFormatter.ISO_OFFSET_DATE_TIME
            ).toInstant()
        );

        service.addConverter(
            String.class,
            UUID.class,
            value -> {
                UUID result = UUID.fromString(value);

                if (!result.toString().equalsIgnoreCase(value)) {
                    throw new IllegalArgumentException(
                        "Expected canonical UUID form"
                    );
                }

                return result;
            }
        );

        return service;
    }
}
~~~

Conversion service này được dùng trực tiếp bởi parser ở phần sau. Nó không được đăng ký như một cấu hình conversion toàn cục, vì các endpoint khác có thể có hợp đồng khác về giá hoặc boolean.

Quy tắc giá cố ý không chấp nhận dấu phẩy thập phân, ký pháp số mũ hoặc số âm. Giới hạn hai chữ số phần lẻ là lựa chọn của endpoint minh họa, không phải quy tắc áp dụng cho mọi loại tiền tệ.

### Thời điểm cần offset rõ ràng

Hai chuỗi:

~~~text
2026-01-01T00:00:00Z
2026-01-01T07:00:00+07:00
~~~

biểu diễn cùng một thời điểm và được chuẩn hóa về `Instant`. Chuỗi không có offset không xác định được cùng một ý nghĩa mà không có quy ước timezone bổ sung.

Khi đặt offset dương trong query string theo cách mã hóa form, dấu `+` phải được mã hóa phù hợp, chẳng hạn `%2B07:00`. Nếu dùng dấu cộng thô, tầng giải mã có thể biến nó thành khoảng trắng.

Các formatter ISO được mô tả trong [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html).

## 5. Model bộ lọc và lỗi có cấu trúc

Bộ lọc sau conversion không còn chứa chuỗi tùy ý:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

public record ProductFilter(
    Set<UUID> ids,
    Set<ProductState> states,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Instant createdFrom,
    Instant createdBefore,
    Boolean available
) {
    public ProductFilter {
        ids = Set.copyOf(ids);
        states = Set.copyOf(states);
    }
}
~~~

Trong model này:

- Set rỗng nghĩa là client không thêm điều kiện membership.
- Null ở một scalar nghĩa là không thêm điều kiện tương ứng.
- False ở `available` vẫn phải được giữ và áp dụng.

Model không tự quyết định SQL, MongoDB criteria hoặc Querydsl expression. Việc đó thuộc adapter truy vấn của module store.

Ta định nghĩa một lỗi không chứa nguyên giá trị đầu vào:

~~~java
public record FilterViolation(
    String parameter,
    String code,
    String message
) {
}
~~~

~~~java
import java.util.List;

public final class InvalidProductFilter extends RuntimeException {

    private final List<FilterViolation> violations;

    public InvalidProductFilter(List<FilterViolation> violations) {
        super("Invalid product filter");
        this.violations = List.copyOf(violations);
    }

    public List<FilterViolation> violations() {
        return violations;
    }
}
~~~

`code` là mã ổn định để client xử lý. `message` giúp diễn giải cho người dùng. Không cần buộc client so khớp nguyên văn một exception message của thư viện conversion.


## 6. Parser kiểm tra cả kiểu và quan hệ điều kiện

Parser dưới đây dùng cùng conversion service cho từng phần tử, không để cơ chế tách CSV làm thay đổi hợp đồng tham số lặp:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.ConversionService;
import org.springframework.util.MultiValueMap;

public final class ProductFilterParser {

    private static final int MAX_VALUES = 50;
    private static final int MAX_VALUE_LENGTH = 128;

    private static final Set<String> ALLOWED = Set.of(
        "id",
        "state",
        "minPrice",
        "maxPrice",
        "createdFrom",
        "createdBefore",
        "available"
    );

    private final ConversionService conversions =
        ProductFilterConversions.create();

    public ProductFilter parse(MultiValueMap<String, String> raw) {
        List<FilterViolation> errors = new ArrayList<>();

        for (String name : raw.keySet()) {
            if (!ALLOWED.contains(name)) {
                errors.add(new FilterViolation(
                    name,
                    "unknown_parameter",
                    "Unsupported filter parameter"
                ));
            }
        }

        Set<UUID> ids = many(
            raw, "id", UUID.class, errors
        );

        Set<ProductState> states = many(
            raw, "state", ProductState.class, errors
        );

        BigDecimal minPrice = single(
            raw, "minPrice", BigDecimal.class, errors
        );

        BigDecimal maxPrice = single(
            raw, "maxPrice", BigDecimal.class, errors
        );

        Instant createdFrom = single(
            raw, "createdFrom", Instant.class, errors
        );

        Instant createdBefore = single(
            raw, "createdBefore", Instant.class, errors
        );

        Boolean available = single(
            raw, "available", Boolean.class, errors
        );

        if (minPrice != null && maxPrice != null
                && minPrice.compareTo(maxPrice) > 0) {
            errors.add(new FilterViolation(
                "minPrice",
                "invalid_range",
                "minPrice must not exceed maxPrice"
            ));
        }

        if (createdFrom != null && createdBefore != null
                && !createdFrom.isBefore(createdBefore)) {
            errors.add(new FilterViolation(
                "createdFrom",
                "invalid_range",
                "createdFrom must be before createdBefore"
            ));
        }

        if (!errors.isEmpty()) {
            throw new InvalidProductFilter(errors);
        }

        return new ProductFilter(
            ids,
            states,
            minPrice,
            maxPrice,
            createdFrom,
            createdBefore,
            available
        );
    }

    private <T> T single(
        MultiValueMap<String, String> raw,
        String name,
        Class<T> target,
        List<FilterViolation> errors
    ) {
        if (!raw.containsKey(name)) {
            return null;
        }

        List<String> values = raw.get(name);

        if (values == null || values.size() != 1) {
            errors.add(new FilterViolation(
                name,
                "expected_single_value",
                "Exactly one value is required when present"
            ));
            return null;
        }

        return convert(name, values.get(0), target, errors);
    }

    private <T> Set<T> many(
        MultiValueMap<String, String> raw,
        String name,
        Class<T> target,
        List<FilterViolation> errors
    ) {
        if (!raw.containsKey(name)) {
            return Set.of();
        }

        List<String> values = raw.get(name);

        if (values == null || values.isEmpty()) {
            errors.add(new FilterViolation(
                name,
                "empty_value",
                "At least one value is required when present"
            ));
            return Set.of();
        }

        if (values.size() > MAX_VALUES) {
            errors.add(new FilterViolation(
                name,
                "too_many_values",
                "At most 50 values are allowed"
            ));
            return Set.of();
        }

        Set<T> result = new LinkedHashSet<>();

        for (int index = 0; index < values.size(); index++) {
            T converted = convert(
                name + "[" + index + "]",
                values.get(index),
                target,
                errors
            );

            if (converted != null) {
                result.add(converted);
            }
        }

        return result;
    }

    private <T> T convert(
        String parameter,
        String raw,
        Class<T> target,
        List<FilterViolation> errors
    ) {
        if (raw == null || raw.isBlank()) {
            errors.add(new FilterViolation(
                parameter,
                "empty_value",
                "A non-blank value is required"
            ));
            return null;
        }

        if (raw.length() > MAX_VALUE_LENGTH) {
            errors.add(new FilterViolation(
                parameter,
                "value_too_long",
                "Value exceeds the endpoint limit"
            ));
            return null;
        }

        try {
            T value = conversions.convert(raw.strip(), target);

            if (value == null) {
                errors.add(new FilterViolation(
                    parameter,
                    "invalid_value",
                    "Invalid value for this filter"
                ));
            }

            return value;
        } catch (ConversionFailedException exception) {
            errors.add(new FilterViolation(
                parameter,
                "invalid_value",
                "Invalid value for this filter"
            ));
            return null;
        }
    }
}
~~~

Có vài chi tiết quan trọng:

1. Parser ghi nhận lỗi của từng phần tử nhưng không trả về một bộ lọc hợp lệ một phần.
2. Scalar lặp bị phát hiện trước khi chọn giá trị.
3. Mọi lỗi được kiểm tra trước khi tạo kết quả để tầng truy vấn sử dụng.
4. Lỗi cấu hình như thiếu converter không được cố ý đổi thành lỗi đầu vào bằng một `catch RuntimeException` quá rộng.
5. Giới hạn số lượng được xét trên số giá trị nhận được trước khi loại trùng.

Các giới hạn của parser là chính sách ứng dụng. Hạ tầng HTTP vẫn cần có giới hạn request, số lượng tham số và kích thước phù hợp; parser không thay thế việc cấu hình hạ tầng đó.

### Khoảng giá và khoảng thời gian có cận khác nhau

Ví dụ chọn:

~~~text
minPrice <= price <= maxPrice
createdFrom <= createdAt < createdBefore
~~~

Khoảng giá có hai cận bằng nhau vẫn có nghĩa: tìm đúng một mức giá.

Khoảng thời gian có cận trên không bao gồm và hai cận bằng nhau được coi là không hợp lệ theo chính sách của endpoint này. Parser không tự đổi chỗ hai cận.

Một API khác có thể chọn trả tập rỗng cho một số khoảng thay vì báo lỗi. Điều cần thiết là tài liệu, validator và truy vấn phải cùng theo một quy ước.

## 7. Chuyển lỗi thành response HTTP có cấu trúc

Controller advice chỉ xử lý exception đầu vào do parser của ví dụ tạo ra:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ProductFilterErrorAdvice {

    @ExceptionHandler(InvalidProductFilter.class)
    public ResponseEntity<ProblemDetail> invalidFilter(
        InvalidProductFilter exception
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "One or more product filter conditions are invalid"
        );

        problem.setTitle("Bad Request");
        problem.setProperty(
            "errors",
            exception.violations()
        );

        return ResponseEntity.badRequest()
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
~~~

Với request:

~~~http
GET /products/search?state=ACTIVE&state=UNKNOWN
~~~

response có thể là:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "One or more product filter conditions are invalid",
  "errors": [
    {
      "parameter": "state[1]",
      "code": "invalid_value",
      "message": "Invalid value for this filter"
    }
  ]
}
~~~

Cấu hình MVC/JSON phù hợp cần render các extension property của `ProblemDetail`. Xem [Spring MVC Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html).

Advice này chưa bao quát mọi lỗi có thể xảy ra trước controller, chẳng hạn body JSON hỏng, lỗi type mismatch của một đối số MVC khác hoặc validation ở method parameter. Nếu API muốn một envelope lỗi thống nhất, cần xử lý những nhóm đó trong chính sách lỗi chung.

Không chuyển lỗi database thành `400` chỉ vì request có bộ lọc. Lỗi cú pháp/điều kiện thuộc client; lỗi cấu hình hoặc hạ tầng cần được phân loại theo nguyên nhân thực.

## 8. Controller chỉ truy vấn sau khi parse thành công

Các cổng dưới đây giữ ví dụ độc lập với JPA, MongoDB hoặc store cụ thể:

~~~java
import java.util.List;

public interface ProductSearchPort {

    List<ProductSummary> search(
        String tenantId,
        ProductFilter filter,
        int limit
    );
}
~~~

~~~java
public record ProductSummary(
    String id,
    String name
) {
}
~~~

~~~java
public interface CurrentTenant {

    String requireTenantId();
}
~~~

Controller:

~~~java
import java.util.List;

import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductSearchController {

    private final ProductFilterParser parser =
        new ProductFilterParser();

    private final ProductSearchPort products;
    private final CurrentTenant currentTenant;

    public ProductSearchController(
        ProductSearchPort products,
        CurrentTenant currentTenant
    ) {
        this.products = products;
        this.currentTenant = currentTenant;
    }

    @GetMapping(
        value = "/products/search",
        produces = "application/json"
    )
    public List<ProductSummary> search(
        @RequestParam MultiValueMap<String, String> parameters
    ) {
        ProductFilter filter = parser.parse(parameters);

        return products.search(
            currentTenant.requireTenantId(),
            filter,
            100
        );
    }
}
~~~

Để chạy ứng dụng thật, cần implementation của `ProductSearchPort`, `CurrentTenant` và cấu hình xác thực/ngữ cảnh phù hợp. Tenant phải đến từ ngữ cảnh server đã kiểm tra, không phải một tham số lọc tùy ý.

Ví dụ dùng giới hạn kết quả cố định 100 để tập trung vào điều kiện lọc. Nó chưa cung cấp tổng hoặc điều hướng phân trang. Nếu bổ sung `page`, `size` hoặc `sort`, phải mở rộng hợp đồng và xử lý chúng ở đúng resolver/chính sách thay vì để parser hiện tại tự suy đoán.

Parser được tái sử dụng, còn danh sách lỗi và tập giá trị là biến cục bộ của mỗi lần parse. Không lưu điều kiện của request hiện tại vào field dùng chung.

## 9. Adapter truy vấn phải giữ đúng ý nghĩa bộ lọc

Implementation của cổng đọc có thể diễn giải điều kiện theo dạng khái niệm:

~~~text
tenant = tenant từ ngữ cảnh server

AND id IN ids                         nếu ids không rỗng
AND state IN states                   nếu states không rỗng
AND price >= minPrice                 nếu có minPrice
AND price <= maxPrice                 nếu có maxPrice
AND createdAt >= createdFrom          nếu có createdFrom
AND createdAt < createdBefore         nếu có createdBefore
AND available = available             nếu available khác null
~~~

Đây là mô tả logic, chưa phải câu SQL chạy trực tiếp.

Khi áp dụng boolean, cần kiểm tra:

~~~java
if (filter.available() != null) {
    // Thêm điều kiện bằng chính giá trị true hoặc false.
}
~~~

Nếu chỉ thêm điều kiện khi `Boolean.TRUE.equals(filter.available())`, request `available=false` có thể bị mất điều kiện.

Cũng cần tôn trọng quy ước set rỗng của model: trong ví dụ nó biểu diễn không có điều kiện membership do client, không phải yêu cầu thực thi một toán tử IN rỗng.

### Hợp lệ nhưng không có kết quả khác với không hợp lệ

Một bộ lọc có thể hoàn toàn hợp lệ nhưng không có sản phẩm phù hợp. Trường hợp đó trả kết quả rỗng theo hợp đồng endpoint, không phải lỗi chuyển đổi.

Không tự coi một tổ hợp như `state=ARCHIVED&available=true` là sai nếu nghiệp vụ chưa cấm nó. Khả năng hai điều kiện không cùng khớp dữ liệu hiện tại khác với một điều kiện không hợp lệ về ngữ nghĩa.

Adapter phải sử dụng API query/parameter binding của module store. Không ghép các giá trị chuỗi đã nhận vào một biểu thức truy vấn thủ công rồi coi conversion là đủ để bảo đảm mọi khía cạnh của truy vấn.


## 10. JSON payload không đi qua cùng một cơ chế conversion

Với một API tìm kiếm bằng JSON:

~~~http
POST /products/search
Content-Type: application/json
~~~

~~~json
{
  "states": ["ACTIVE", "PAUSED"],
  "minPrice": 10.00,
  "maxPrice": 100.00,
  "available": false
}
~~~

body được đọc bởi `HttpMessageConverter`. Cơ chế deserialization JSON và cấu hình của nó khác với việc parser gọi `ConversionService` trên từng chuỗi query.

Ví dụ một request DTO:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record ProductSearchRequest(
    @Size(min = 1, max = 50)
    Set<@NotNull UUID> ids,

    @Size(min = 1, max = 50)
    Set<@NotNull ProductState> states,

    @DecimalMin("0.00")
    @Digits(integer = 12, fraction = 2)
    BigDecimal minPrice,

    @DecimalMin("0.00")
    @Digits(integer = 12, fraction = 2)
    BigDecimal maxPrice,

    Instant createdFrom,
    Instant createdBefore,
    Boolean available
) {
}
~~~

Khi dùng `@Valid @RequestBody ProductSearchRequest request` trong một handler, cần có Bean Validation provider và converter JSON phù hợp. Việc đọc `Instant` còn cần cấu hình hỗ trợ thời gian của converter đang dùng.

Trong DTO minh họa:

- Collection không được rỗng nếu có giá trị; null vẫn được phép vì field là tùy chọn.
- Phần tử null trong collection bị validation từ chối.
- Giá được kiểm tra không âm và số chữ số.
- Quan hệ giữa min/max hoặc hai thời điểm vẫn cần validator liên trường.

Với `Set`, constraint `@Size` kiểm tra số phần tử sau khi deserialization đã tạo tập, không kiểm tra độ dài mảng JSON trước khi loại trùng. Nếu cần giới hạn trên số giá trị được gửi như parser query ở trên, nên nhận `List`, kiểm tra kích thước trước rồi mới tạo set; giới hạn body cũng cần được cấu hình ở hạ tầng phù hợp.

Tên field JSON không được hỗ trợ và các khóa JSON trùng nhau chịu chính sách của JSON parser/converter. Một record không tự bảo đảm mọi field lạ đều tạo lỗi. Nếu hợp đồng yêu cầu từ chối chúng, cần cấu hình và kiểm thử cơ chế đó riêng; nhiều giá trị trong payload nên được biểu diễn bằng mảng đã định nghĩa.

Nếu hợp đồng muốn phân biệt field không xuất hiện với field có JSON null, một record chứa các giá trị nullable thông thường chưa đủ để giữ thông tin hiện diện đó. Cần model hoặc cơ chế theo dõi presence thích hợp.

Không stringify mọi field của payload rồi đưa lại vào parser query chỉ để dùng chung code. Nên dùng chung phần validation/ngữ nghĩa của model có kiểu, còn cú pháp HTTP được xử lý ở từng adapter.

### Các nhóm lỗi có thể xảy ra ở thời điểm khác nhau

| Nhóm | Ví dụ |
|---|---|
| Không đọc được payload | JSON hỏng hoặc giá trị không chuyển được về kiểu đích |
| Constraint của một field | Giá âm hoặc collection quá lớn |
| Constraint liên trường | minPrice lớn hơn maxPrice |
| Constraint nghiệp vụ | Toán tử không được hỗ trợ với trường đã chọn |
| Phạm vi dữ liệu | Người gọi không được áp dụng một điều kiện hoặc đọc một tập dữ liệu |

Bean Validation thường diễn ra sau khi body đã được deserialize thành object. Vì vậy, không kỳ vọng một constraint nghiệp vụ luôn xử lý được chuỗi đã làm converter thất bại trước đó.

Xem [RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html) và [Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).

### Projected payload của Spring Data

Spring Data Web Support cũng có thể bind payload vào interface projection với `@ProjectedPayload` và các biểu thức JSONPath, khi có các dependency tương ứng.

Ví dụ một interface đọc dữ liệu nguồn:

~~~java
import java.util.List;

import org.springframework.data.web.JsonPath;
import org.springframework.data.web.ProjectedPayload;

@ProjectedPayload
public interface SearchPayload {

    @JsonPath("$.states")
    List<String> getStates();

    @JsonPath("$.minPrice")
    String getMinPrice();
}
~~~

Ví dụ này chỉ mô tả cách lấy giá trị từ payload có cấu trúc phù hợp; nó chưa kiểm tra trạng thái, giá, số lượng hoặc quan hệ giữa điều kiện.

Sau extraction, cần đưa dữ liệu qua các bước conversion/validation đã chọn trước khi tạo truy vấn. Việc có getter trong projection không chứng minh giá trị đã đáp ứng hợp đồng nghiệp vụ.

Hạ tầng đăng ký và dependency được mô tả trong [Spring Data Web Databinding Support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html#core.web.binding).

## 11. Querydsl: first và all phải khớp ngữ nghĩa nhiều giá trị

Với store có tích hợp Querydsl, Spring Data có thể tạo `Predicate` từ query string thông qua web support. Chức năng này cần hạ tầng Querydsl và domain/Q-type phù hợp; không áp dụng mặc nhiên cho mọi repository.

`QuerydslBindings` cho phép tùy biến:

- `first(...)` xử lý một giá trị, lấy giá trị đầu khi có nhiều giá trị.
- `all(...)` tiếp nhận các giá trị để xác định một predicate chung.

Do đó, dùng `first(...)` không có nghĩa scalar lặp sẽ bị từ chối. Nếu hợp đồng cấm lặp, cần kiểm tra cardinality ở một vị trí phù hợp còn quan sát được request thô.

Ví dụ customizer cho hai property membership:

~~~java
import java.util.Optional;

import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;

public final class PublicProductBindings
    implements QuerydslBinderCustomizer<QProduct> {

    @Override
    public void customize(
        QuerydslBindings bindings,
        QProduct root
    ) {
        bindings.excludeUnlistedProperties(true);
        bindings.including(root.id, root.state);

        bindings.bind(root.id)
            .all((path, values) ->
                Optional.of(path.in(values))
            );

        bindings.bind(root.state)
            .all((path, values) ->
                Optional.of(path.in(values))
            );
    }
}
~~~

`QProduct` ở đoạn này là Q-type đã được tạo cho domain của ứng dụng có hỗ trợ Querydsl. Đây là cấu hình thay thế minh họa, không phải thành phần bắt buộc của parser ở phần 6. Khi dùng, cần gắn customizer vào binding thực tế, chẳng hạn qua thuộc tính `bindings` của `@QuerydslPredicate`.

Cho phép một property được bind khác với cam kết “property lạ luôn tạo 400”. Một allowlist giới hạn các đường dẫn có thể tham gia binding, nhưng không tự thay thế chính sách validation lỗi đầu vào.

Ngoài ra, resolver tạo predicate có thể chạy trước khi thân controller được gọi. Đừng giả định một bước kiểm tra raw parameter ở thân controller luôn diễn ra trước mọi lỗi conversion của resolver.

Hợp đồng API của các phương thức được mô tả trong [QuerydslBindings](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/querydsl/binding/QuerydslBindings.html).

### Không suy ra range từ hai giá trị một cách ngầm định

Một binding nhận hai số có thể được thiết kế thành:

- Hai giá trị equality nối OR.
- Hai cận của một khoảng.
- Một tổ hợp không hợp lệ nếu property chỉ được chọn một lần.

Tên tham số, số phần tử và thứ tự cận phải được công bố. Không mặc định mọi collection hai phần tử đều là khoảng.

Với khoảng thời gian trong bài, tham số có tên riêng `createdFrom` và `createdBefore` giúp ý nghĩa rõ hơn việc phụ thuộc vị trí trong một danh sách không được mô tả.

## 12. Query by Example không thay thế mọi bộ lọc

Query by Example phù hợp với một số nhu cầu tìm theo thuộc tính của probe và matcher. Nó không tự biến mọi model bộ lọc thành một ngôn ngữ hỗ trợ IN, khoảng và nhóm điều kiện tùy ý.

Đừng sao chép `ProductFilter` vào một entity rồi kỳ vọng:

- Set trạng thái trở thành IN trên một scalar.
- minPrice/maxPrice tự biến thành hai cận của cùng property.
- Một nhóm OR bên trong được giữ nguyên.
- Primitive mặc định luôn được hiểu là không có điều kiện.

Đặc biệt, primitive như boolean false có thể bị coi là giá trị cần match, trong khi nullable wrapper giúp giữ khái niệm “không có điều kiện” theo thiết kế thích hợp.

Hãy chọn abstraction truy vấn theo khả năng store và ngữ nghĩa cần thực thi. Tham khảo giới hạn trong [Spring Data Commons — Query by Example](https://docs.spring.io/spring-data/commons/reference/query-by-example.html).

## 13. Kiểm thử request đúng và request sai

Một unit test converter chỉ kiểm tra phép đổi kiểu đơn lẻ. Cần kiểm thử thêm đường đi từ HTTP để xác nhận tham số lặp được giữ, advice trả đúng lỗi và request sai không gọi tầng dữ liệu.

Ví dụ sử dụng controller, parser và advice ở các phần trước:

~~~java
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class ProductFilterWebTest {

    private final ProductSearchPort products =
        mock(ProductSearchPort.class);

    private MockMvc web() {
        CurrentTenant tenant = () -> "tenant-a";

        return standaloneSetup(
                new ProductSearchController(products, tenant)
            )
            .setControllerAdvice(new ProductFilterErrorAdvice())
            .build();
    }

    @Test
    void keepsSeveralStatesAndFalse() throws Exception {
        when(products.search(
                eq("tenant-a"),
                any(ProductFilter.class),
                eq(100)
            ))
            .thenReturn(List.of());

        web().perform(get("/products/search")
                .param("state", "ACTIVE", "PAUSED")
                .param("available", "false"))
            .andExpect(status().isOk());

        ArgumentCaptor<ProductFilter> captured =
            ArgumentCaptor.forClass(ProductFilter.class);

        verify(products).search(
            eq("tenant-a"),
            captured.capture(),
            eq(100)
        );

        assertEquals(
            Set.of(ProductState.ACTIVE, ProductState.PAUSED),
            captured.getValue().states()
        );

        assertEquals(
            Boolean.FALSE,
            captured.getValue().available()
        );
    }

    @Test
    void rejectsAnInvalidElementWithoutQuerying() throws Exception {
        web().perform(get("/products/search")
                .param("state", "ACTIVE", "UNKNOWN"))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON
            ))
            .andExpect(jsonPath("$.errors[0].parameter")
                .value("state[1]"))
            .andExpect(jsonPath("$.errors[0].code")
                .value("invalid_value"));

        verifyNoInteractions(products);
    }

    @Test
    void rejectsRepeatedScalar() throws Exception {
        web().perform(get("/products/search")
                .param("minPrice", "10", "20"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].code")
                .value("expected_single_value"));

        verifyNoInteractions(products);
    }

    @Test
    void rejectsAnInvertedRange() throws Exception {
        web().perform(get("/products/search")
                .param("minPrice", "100")
                .param("maxPrice", "10"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].code")
                .value("invalid_range"));

        verifyNoInteractions(products);
    }
}
~~~

Mẫu này cần JUnit, Mockito, spring-test, JSONPath và converter JSON phù hợp. Đây là code thực hành, không phải báo cáo đã chạy test trên ứng dụng store cụ thể.

Standalone setup kiểm tra các thành phần được đưa trực tiếp vào test. Nó chưa chứng minh authentication, cấu hình converter toàn cục hoặc Querydsl resolver trong application context đã hoạt động đúng.

### Ma trận đầu vào cần kiểm tra thêm

| Request hoặc tình huống | Kết quả theo hợp đồng ví dụ |
|---|---|
| Không có filter | Không có điều kiện client; vẫn có phạm vi server và giới hạn kết quả |
| `available=false` | Giữ điều kiện false |
| `available=maybe` | 400 |
| `state=ACTIVE,PAUSED` | 400 vì endpoint không dùng CSV |
| `state=ACTIVE&state=ACTIVE` | Hợp lệ, loại trùng |
| `state=` | 400 |
| `minPrice=` | 400 |
| `minPrice=-1` | 400 |
| `minPrice=1e3` | 400 theo cú pháp giá của query endpoint này |
| `minPrice=10&maxPrice=10` | Hợp lệ, khoảng giá bằng một giá trị |
| Hai cận thời gian bằng nhau | 400 theo chính sách khoảng của ví dụ |
| Thời điểm không có offset | 400 |
| Hai thời điểm khác offset nhưng cùng instant | Chuẩn hóa về cùng thời điểm trước khi so sánh |
| UUID không đúng dạng chuẩn | 400 |
| Hơn 50 giá trị của một collection | 400 |
| Tên tham số không được hỗ trợ | 400 |
| Bộ lọc hợp lệ không có bản ghi phù hợp | Kết quả rỗng, không phải lỗi conversion |

Với repository thật, cần kiểm tra predicate cuối cùng giữ đúng AND/IN, các cận thời gian và tenant. Unit test parser không chứng minh adapter truy vấn đã áp dụng model đúng.

## 14. Những lỗi dễ làm thay đổi ý nghĩa truy vấn

| Cách làm | Hệ quả |
|---|---|
| Đọc bằng map scalar rồi bỏ mất các giá trị lặp | Không còn kiểm tra được đúng cardinality |
| Chọn phần tử đầu mà không công bố | Các thành phần có thể hiểu request khác nhau |
| Bỏ phần tử collection không chuyển được | Tạo truy vấn khác yêu cầu thay vì báo lỗi |
| Chuyển boolean lạ thành false | Lỗi nhập liệu trở thành điều kiện thật |
| Đổi rỗng thành null cho mọi field | Không còn phân biệt thiếu với giá trị sai |
| Tự đổi chỗ hai cận | Che một lỗi của client và làm khó chẩn đoán |
| Dùng Double cho giá cần độ chính xác thập phân | Có thể làm sai ngữ nghĩa so sánh |
| Dùng timezone mặc định của server một cách ngầm định | Cùng request có thể đổi nghĩa giữa môi trường |
| Bỏ qua mọi tên property không biết | Có thể vô tình làm bộ lọc rộng hơn |
| Cho client thay tenant qua query | Trộn điều kiện lựa chọn với phạm vi được phép |
| Catch mọi RuntimeException thành 400 | Che lỗi lập trình hoặc cấu hình |
| Ghép request thành câu query thô | Bỏ qua ranh giới query binding của store |

Không phải mọi endpoint đều cần một parser riêng dài như ví dụ. Với bộ lọc đơn giản, typed request DTO và binding sẵn có có thể đủ. Khi dùng chúng, vẫn cần xác định những quy tắc mà binding mặc định không kiểm tra, nhất là scalar lặp, trường lạ và quan hệ giữa nhiều field.

## 15. Bài thực hành

Thiết kế một endpoint lọc dữ liệu theo khả năng của một module store:

1. Liệt kê tên tham số public và tập toán tử được phép.
2. Đánh dấu rõ scalar, collection và quy tắc cho tham số lặp.
3. Viết quy ước cho thiếu, rỗng, null và false.
4. Chọn định dạng số, enum và thời điểm không phụ thuộc ngầm vào môi trường.
5. Chuyển đổi từng giá trị về kiểu đích rồi kiểm tra quan hệ liên trường.
6. Trả mã lỗi ổn định và vị trí lỗi của từng phần tử.
7. Bảo đảm một phần tử sai làm request thất bại theo hợp đồng đã chọn.
8. Áp dụng phạm vi dữ liệu từ ngữ cảnh server độc lập với filter của client.
9. Nếu dùng Querydsl hoặc QBE, đối chiếu khả năng thật với từng toán tử cần hỗ trợ.
10. Kiểm thử cả request hợp lệ không có dữ liệu lẫn request không hợp lệ.
11. Xác minh request sai không gọi tầng truy vấn.
12. Công bố giới hạn số lượng và chính sách nâng cấp hợp đồng.

Điều cần giữ xuyên suốt là: **dữ liệu HTTP được đọc đúng số lượng, chuyển sang đúng kiểu, kiểm tra đúng ngữ nghĩa rồi mới trở thành điều kiện truy vấn; khả năng của repository hoặc store không thay thế hợp đồng và validation ở biên web.**
