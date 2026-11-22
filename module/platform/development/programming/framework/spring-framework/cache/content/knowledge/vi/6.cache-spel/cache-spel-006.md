# Xử lý đối tượng null trong biểu thức SpEL của Spring Cache

> **Ngữ cảnh:** Spring Framework — mục **Biểu thức SpEL**. Bài học tập trung vào cách xử lý giá trị `null` khi truy cập thuộc tính, gọi phương thức và tính điều kiện trong SpEL, nhất là ở `key`, `condition` và `unless` của annotation Spring Cache.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Chỉ ra khi nào truy cập vào đối tượng `null` gây lỗi đánh giá SpEL.
- Sử dụng toán tử safe navigation `?.`, Elvis `?:`, toán tử ba ngôi và điều kiện logic ngắn mạch.
- Xử lý chuỗi thuộc tính nhiều cấp, đầu vào null, kết quả null và chuỗi rỗng.
- Viết biểu thức cho `@Cacheable` với `key`, `condition`, `unless` đúng thời điểm và tránh khóa cache null.
- Thực thi ví dụ Java 17 dùng `spring-expression`; phân biệt ví dụ thử cú pháp với kiểm thử cache annotation thực tế.

## 2. Vì sao đối tượng null làm biểu thức SpEL lỗi?

Spring Expression Language (SpEL) được dùng để đọc thuộc tính, gọi phương thức, so sánh và xây dựng giá trị từ object. Xét một cấu trúc:

```text
request
  └── customer
        └── address
              └── city
```

Ở thực tế, `request`, `customer` hoặc `address` đều có thể null. Biểu thức sau mặc định tin rằng mọi đối tượng đều tồn tại:

```spel
#request.customer.address.city
```

Nếu một đối tượng ở giữa bằng null, việc tiếp tục truy cập thuộc tính thường làm SpEL ném `SpelEvaluationException`. Điều này khác với **biểu thức trả về null một cách hợp lệ**: lỗi đánh giá khiến thao tác cache có thể thất bại, còn một biểu thức null-safe trả null và để các bước xử lý sau quyết định.

Các nguồn null điển hình gồm đối số phương thức không được cung cấp, thuộc tính chưa khởi tạo, đối tượng không tìm thấy trong cơ sở dữ liệu, giá trị `Optional.empty()` hoặc collection vắng mặt. Với cache, cần phân biệt rõ ba vấn đề: **biểu thức đánh giá an toàn**, **khóa lưu trữ hợp lệ**, và **giá trị có được phép lưu**.

## 3. Toán tử safe navigation `?.`

Đặt `?.` trước việc đọc một thuộc tính hoặc gọi một phương thức trên đối tượng có khả năng null:

```spel
#request?.customer
#request?.customer?.address
#request?.customer?.address?.city
#request?.customer?.getName()
```

Đối với một thao tác có dấu `?.`, nếu toán hạng bên trái bằng null thì kết quả của thao tác đó là null thay vì truy cập đối tượng null. Nếu bên trái không null, SpEL thực hiện truy cập bình thường.

**Phải bảo vệ từng mắt xích có thể null.** So sánh:

```spel
#request?.customer.address.city
#request?.customer?.address?.city
```

Dòng thứ nhất **vẫn có thể lỗi**: sau khi `#request?.customer` trả null, phần `.address.city` của biểu thức ghép vẫn được đánh giá. Dòng thứ hai dùng safe navigation ở các bước tiếp theo nên an toàn nếu `request`, `customer` hoặc `address` bị null.

| Trường hợp | Biểu thức | Kết quả |
| --- | --- | --- |
| `request == null` | `#request?.customer` | `null` |
| `customer == null` | `#request?.customer?.address?.city` | `null` |
| `address == null` | `#request?.customer?.address?.city` | `null` |
| Có đủ các đối tượng | `#request?.customer?.address?.city` | Giá trị thành phố |
| Getter tự ném exception | `#request?.customer` | Vẫn có thể ném lỗi từ getter |

Safe navigation **không** che lỗi sai tên thuộc tính, sai kiểu, lỗi do getter tự ném exception, phần truy cập không có dấu `?.` ở phía sau, hoặc lỗi nghiệp vụ bên trong phương thức.

## 4. Toán tử Elvis `?:` — chọn giá trị dự phòng

Elvis trong SpEL cho phép viết `a ?: b`. Nếu `a` null **hoặc là chuỗi rỗng**, SpEL chọn `b`:

```spel
#request?.customer?.name ?: 'Khách'
#request?.customer?.address?.city ?: 'Chưa rõ'
```

Ví dụ:

| Giá trị tên | `#name ?: 'Khách'` |
| --- | --- |
| `null` | `Khách` |
| `""` | `Khách` |
| `"Lan"` | `Lan` |

Cẩn trọng: Elvis của SpEL coi chuỗi rỗng như giá trị thiếu. Nếu chuỗi rỗng phải được giữ nguyên vì nghiệp vụ, dùng điều kiện ba ngôi tường minh:

```spel
#name == null ? 'Khách' : #name
```

**Fallback phù hợp cho hiển thị** chưa chắc phù hợp cho khóa cache. Ví dụ `#p0?.id ?: 'MISSING'` sẽ gom mọi đầu vào thiếu ID thành một khóa `MISSING`, có thể gây va chạm khóa, trả nhầm dữ liệu giữa người dùng hoặc tenant. Với khóa cache, thường nên **bỏ caching khi thiếu định danh** hoặc xác thực đầu vào, thay vì dùng một sentinel chung.

## 5. Toán tử ba ngôi và đánh giá logic ngắn mạch

SpEL hỗ trợ `condition ? trueValue : falseValue`:

```spel
#request == null ? 'empty' : #request.customerId
```

Dùng toán tử ba ngôi khi cần hai nhánh nghiệp vụ khác nhau. Vẫn phải bảo vệ các giá trị lồng nhau nếu nhánh được chọn có thể gặp null.

Các toán tử `and`/`&&` và `or`/`||` hỗ trợ đánh giá ngắn mạch. Với AND, nếu vế đầu false thì vế sau không cần chạy; với OR, nếu vế đầu true thì vế sau không cần chạy:

```spel
#request != null && #request.customer != null
#request == null || #request.customer == null
#request != null and #request.customer != null
```

Đối với điều kiện cache, hai cách sau có thể tương đương khi accessor có hành vi bình thường:

```spel
#p0 != null && #p0.customer != null && #p0.customer.id != null
#p0?.customer?.id != null
```

Cả hai kiểm tra có định danh để quyết định có cache hay không. Cách dùng `?.` súc tích; cách dùng điều kiện tường minh thuận tiện hơn khi kết hợp nhiều kiểm tra nghiệp vụ.

## 6. SpEL trong Spring Cache: mỗi thuộc tính có thời điểm đánh giá khác nhau

SpEL do `SpelExpressionParser` tự đánh giá và SpEL trong annotation cache dùng cú pháp chung, nhưng **cache evaluation context** có các giá trị đặc thù:

| Biến | Ý nghĩa |
| --- | --- |
| `#p0` hoặc `#a0` | Tham số đầu tiên của phương thức |
| `#p1` hoặc `#a1` | Tham số thứ hai |
| `#root.args[0]` | Tham số đầu tiên qua root object |
| `#root.methodName` | Tên phương thức |
| `#root.target` | Đối tượng đích của lời gọi |
| `#result` | Kết quả sau khi gọi phương thức, **chỉ ở những biểu thức được phép** |

Tên biến theo tham số như `#request` cần thông tin parameter name trong bytecode; `#p0` và `#a0` giúp ví dụ ít phụ thuộc cờ biên dịch hơn.

Bảng thời điểm:

| Annotation/thuộc tính | Thời điểm | Có `#result`? |
| --- | --- | --- |
| `@Cacheable.condition` | Trước khi quyết định truy cập cache | Không |
| `@Cacheable.key` | Khi tạo key để tra và lưu cache | Không |
| `@Cacheable.unless` | Sau khi có kết quả của lần gọi thực sự | Có |
| `@CachePut.key` | Khi ghi kết quả vào cache | Có thể sử dụng |
| `@CacheEvict` sau invocation | Sau khi phương thức hoàn tất | Có thể sử dụng |
| `@CacheEvict(beforeInvocation = true)` | Trước khi gọi phương thức | Không |

Điều quan trọng: **`@Cacheable(key = "#result?.id")` sai về thời điểm**, vì framework cần key *trước* khi biết kết quả. Dấu `?.` không thể sửa việc `#result` chưa được cung cấp trong context. Ngược lại, `unless = "#result == null"` hợp lệ để từ chối lưu kết quả null **sau khi chạy phương thức**.

Với kiểu trả về được Spring Cache hỗ trợ như `Optional<Customer>`, `#result` trong ngữ cảnh cache sau lời gọi đề cập đến **giá trị nghiệp vụ đã được unwrap**, hoặc null nếu Optional rỗng. Không mặc định viết `#result.isPresent()` trong `unless` như thể đây là một đối tượng Optional.

## 7. Ví dụ Spring Cache: bỏ caching khi thiếu input, tránh lưu null result

Giả sử một dịch vụ Spring nhận `LookupRequest` chứa ID và tìm `Customer` qua repository. Đây là **đoạn minh họa đặt bên trong một bean Spring đã có `LookupRequest`, `Customer` và `repository`**; nó chưa phải chương trình Java độc lập:

```java
@Cacheable(
    cacheNames = "customers",
    condition = "#p0 != null && #p0.id != null",
    key = "#p0.id",
    unless = "#result == null"
)
public Customer findCustomer(LookupRequest request) {
    if (request == null || request.getId() == null) {
        return null;
    }
    return repository.findById(request.getId()).orElse(null);
}
```

Luồng xử lý:

1. Nếu request null, `condition` là false nên Spring **không dùng cache**. Phương thức vẫn được gọi và phải tự xử lý null ở phía Java.
2. Nếu request không null nhưng ID null, `condition` vẫn false; tránh sinh key thiếu ID.
3. Nếu request và ID hợp lệ, Spring tính `key` rồi tra cache. Cache hit có thể trả kết quả mà không chạy thân phương thức.
4. Cache miss gọi repository. Nếu repository không tìm thấy, kết quả null làm `unless` trả true và **không lưu mục cache đó**.
5. Lần gọi tiếp theo với ID không tồn tại có thể tiếp tục miss, cho đến khi có dữ liệu mới hoặc thay đổi điều kiện.

Ở đây `key = "#p0.id"` an toàn khi caching được bật vì `condition` đã kiểm tra không null. Có thể dùng `key = "#p0?.id"` cho cú pháp null-safe, nhưng **giá trị biểu thức là null vẫn không tạo được một explicit cache key hợp lệ** trong những trường hợp Spring kiểm tra key; tốt nhất là không để bước sinh key xảy ra khi thiếu ID.

Nếu chỉ cache kết quả có trạng thái không null, có thể viết:

```java
@Cacheable(
    cacheNames = "customers",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result?.status == null"
)
public Customer findCustomerById(String id) {
    return repository.findById(id).orElse(null);
}
```

Dấu `?.` bảo vệ khi kết quả null. Biểu thức `unless` là **điều kiện cấm lưu**: nếu kết quả null hoặc trạng thái null thì nó bằng true và bỏ lưu. Cần xác minh `status` thực sự là thuộc tính có thể đọc được, và key ID phân biệt đúng dữ liệu.

### Phân biệt null key, null result và null parameter

Đây là ba trường hợp độc lập:

- **Null parameter**: client gọi phương thức với một đối số null. Điều này không tự chứng minh default key generator trả null; `SimpleKeyGenerator` có logic riêng cho 0, 1 và nhiều tham số.
- **Null key từ biểu thức tường minh**: `key = "#p0?.id"` có thể trả null khi ID vắng mặt; Spring Cache có thể báo lỗi kiểu `Null key returned for cache operation`, mặc dù phần truy cập SpEL đã an toàn.
- **Null result**: phương thức chạy xong trả null. Cache có lưu được hay không tùy adapter/provider và chính sách; `unless = "#result == null"` giúp chủ động loại kết quả đó khỏi việc lưu.

Tương tự, `condition = "#p0 != null"` **không làm phương thức nghiệp vụ tự an toàn**. Khi condition false, mã Java vẫn chạy; nếu có `request.getId()` trên request null mà không tự kiểm tra, Java vẫn có thể ném lỗi.

## 8. Ví dụ chạy độc lập Java 17: thực nghiệm cú pháp SpEL

Để phân biệt lỗi cú pháp và dữ liệu null, ta thử trực tiếp thư viện `spring-expression`, không cần khởi tạo Spring Boot hay Redis.

### 8.1. Cấu trúc dự án

```text
spel-null-demo/
├── pom.xml
└── src/main/java/demo/SpelNullDemo.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spel-null-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-expression</artifactId>
            <version>6.2.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.SpelNullDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-expression:6.2.1` là một bản cụ thể giúp ví dụ có thể tái tạo trên JDK 17. Với ứng dụng Spring Boot có sẵn, nên quản lý các module Spring thống nhất qua parent hoặc BOM của phiên bản Boot dự án; không tự pin mỗi module một phiên bản khác nhau.

### 8.3. `src/main/java/demo/SpelNullDemo.java`

```java
package demo;

import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class SpelNullDemo {

    public static final class Address {
        private final String city;

        public Address(String city) {
            this.city = city;
        }

        public String getCity() {
            return city;
        }
    }

    public static final class User {
        private final String name;
        private final Address address;

        public User(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        public String getName() {
            return name;
        }

        public Address getAddress() {
            return address;
        }
    }

    private static Object evaluate(
            ExpressionParser parser,
            StandardEvaluationContext context,
            String expression) {
        return parser.parseExpression(expression).getValue(context);
    }

    public static void main(String[] args) {
        ExpressionParser parser = new SpelExpressionParser();
        StandardEvaluationContext context = new StandardEvaluationContext();

        context.setVariable("user", null);
        System.out.println("nullName="
                + evaluate(parser, context, "#user?.name"));
        System.out.println("fallback="
                + evaluate(parser, context, "#user?.name ?: 'guest'"));
        System.out.println("guard="
                + evaluate(parser, context,
                        "#user != null and #user.name != null"));

        context.setVariable("user", new User("", null));
        System.out.println("emptyName="
                + evaluate(parser, context, "#user?.name ?: 'guest'"));
        System.out.println("missingCity="
                + evaluate(parser, context,
                        "#user?.address?.city ?: 'unknown'"));

        context.setVariable("user", new User("Lan", new Address("Ha Noi")));
        System.out.println("city="
                + evaluate(parser, context, "#user?.address?.city"));
    }
}
```

### 8.4. Biên dịch và chạy

Cần JDK 17+, Maven 3.9+ và khả năng tải dependency khi chạy lần đầu. Tại thư mục `spel-null-demo`:

```bash
java -version
mvn -q compile exec:java
```

Các dòng do **chính chương trình** in ra (bỏ qua thông báo Maven/plugin):

```text
nullName=null
fallback=guest
guard=false
emptyName=guest
missingCity=unknown
city=Ha Noi
```

Giải thích:

- `nullName=null`: safe navigation trả Java null, phép nối String in chữ `null`.
- `fallback=guest`: Elvis thay một giá trị null bằng chuỗi dự phòng.
- `guard=false`: AND dừng ở điều kiện đầu sai, không truy cập `#user.name`.
- `emptyName=guest`: trong SpEL, Elvis cũng xem chuỗi rỗng như trường hợp cần fallback.
- `missingCity=unknown`: `user` tồn tại nhưng `address` null; `?.` thứ hai bảo vệ.
- `city=Ha Noi`: các nút tồn tại thì biểu thức trả thuộc tính thật.

**Giới hạn thực nghiệm:** chương trình kiểm tra **SpEL parser thuần**. Nó không tạo `CacheManager`, không kiểm chứng Spring proxy, không đo cache hit/miss. Khi đưa biểu thức vào annotation cache, phải kiểm tra thêm thời điểm đánh giá và hành vi provider.

## 9. Null-safe indexing, collection selection và projection

Ngoài đọc thuộc tính, SpEL hỗ trợ các dạng null-safe khác (cú pháp indexing null-safe có từ Spring Framework 6.2):

| Mục đích | Cú pháp | Khi đối tượng nguồn null |
| --- | --- | --- |
| Truy cập thuộc tính | `#user?.name` | Trả null |
| Gọi phương thức | `#user?.getName()` | Trả null |
| Lấy phần tử theo index | `#items?.[0]` | Trả null |
| Lọc collection | `#items?.?[active]` | Trả null |
| Chọn phần tử đầu phù hợp | `#items?.^[active]` | Trả null |
| Chọn phần tử cuối phù hợp | `#items?.$[active]` | Trả null |
| Chiếu các phần tử | `#items?.![name]` | Trả null |

**Hai giới hạn cần nhớ:** null-safe indexing không tự cứu truy cập index 0 của một danh sách **không null nhưng rỗng**; và nội dung bên trong selection/projection vẫn có thể lỗi nếu từng phần tử có giá trị null ở thuộc tính khác.

Một ví dụ ghép nhiều thao tác:

```spel
#items?.^[active]?.name ?: 'none'
```

Nếu items null, hoặc không có phần tử phù hợp, hoặc tên null/chuỗi rỗng, kết quả dùng fallback `none`. Các phần tử thực sự được chọn phải có thuộc tính `active` và `name` hợp lệ.

Với `Optional`: sự hỗ trợ null-safe trực tiếp trên một đối tượng `Optional` có khác biệt theo phiên bản; Spring Framework **7.0** bổ sung cơ chế truy cập null-safe và unwrap trên Optional trong SpEL. Đừng mặc định cú pháp hiện đại đó hoạt động y hệt khi dùng Spring cũ. Đây là vấn đề riêng với quy tắc `#result` unwrap trong annotation Spring Cache.

## 10. Lỗi thường gặp và cách xử lý

### Sai 1: Dùng một dấu safe navigation rồi truy cập tiếp bằng dấu chấm thường

- **Sai:** `#p0?.customer.address.city`.
- **Đúng với các nút nullable:** `#p0?.customer?.address?.city`.

Dấu `?.` chỉ bảo vệ **thao tác tại vị trí đó**, không tự làm toàn bộ chuỗi tiếp theo null-safe.

### Sai 2: Dùng Elvis tạo khóa chung cho nhiều đối tượng

- **Nguy hiểm:** `key = "#p0?.id ?: 'unknown'"`.
- **An toàn hơn khi thiếu ID nghĩa là không được cache:** `condition = "#p0?.id != null"`, kèm key đúng cho đầu vào hợp lệ.

Thiết kế key phải phản ánh tenant, locale, vai trò và các đối số làm thay đổi kết quả, nếu nghiệp vụ phụ thuộc chúng.

### Sai 3: Dùng `#result` trong `key` của `@Cacheable`

`#result` chưa có trước lời gọi; phải dùng đối số phương thức, hoặc chọn cơ chế cập nhật cache sau invocation phù hợp. Safe navigation không giải quyết được sai ngữ cảnh.

### Sai 4: Viết ngược ý nghĩa của `unless`

Muốn **không lưu kết quả null**, dùng:

```java
@Cacheable(cacheNames = "customers", key = "#p0",
           unless = "#result == null")
```

`unless` trả true nghĩa là **không lưu**; `unless = "#result != null"` sẽ cấm lưu những kết quả có dữ liệu, thường sai mục tiêu.

### Sai 5: Cho rằng `condition` làm method không chạy

Nếu condition false, Spring Cache bỏ qua caching, nhưng mã Java trong phương thức vẫn thực thi. Thân phương thức phải tự validate hoặc xử lý null. Chỉ `@Cacheable` hit mới có thể bỏ qua thân phương thức nhờ interception.

### Sai 6: Dùng logic null-safe để che exception thật

Getter tự ném `IllegalStateException` không được `?.` biến thành null. Sai tên thuộc tính hoặc thiếu getter cần xử lý theo cấu trúc Java và stacktrace; không giải bằng cách rải thêm `?.`.

### Sai 7: Test SpEL nhưng chưa test cache thực

Thử parser riêng chỉ xác minh cú pháp và kết quả biểu thức. Một integration test thực tế cần cấu hình `@EnableCaching`, provider, lấy bean qua Spring proxy và assert rằng cùng key thì phương thức gốc có thể không chạy lần hai.

## 11. Cách kiểm thử có kiểm soát

Nên chuẩn bị các ca sau với cùng biểu thức:

| Ca | Đầu vào/kết quả | Hành vi mong đợi |
| --- | --- | --- |
| 1 | Đối tượng gốc null | Safe navigation trả null, condition có thể false |
| 2 | Thuộc tính trung gian null | Biểu thức null-safe đầy đủ không lỗi |
| 3 | String rỗng | Elvis dùng fallback |
| 4 | Đủ giá trị hợp lệ | Đọc đúng thuộc tính, sinh key đúng |
| 5 | Method trả null | `unless` phù hợp bỏ lưu |
| 6 | ID khác nhau | Không vô tình dùng chung một khóa cache |
| 7 | ID giống nhau, lần thứ hai | Nếu cache hit thì bỏ qua xử lý gốc |
| 8 | Cache bị eviction/TTL | Có thể miss và chạy lại thân phương thức |

Trong thực tế, kiểm tra cả `CacheManager` thực sự được Spring chọn và dữ liệu cache tồn tại theo key. Tránh đưa một sentinel chung vào key khi có phân quyền hoặc dữ liệu theo tenant.

## 12. Bài tập tự kiểm tra

**Câu 1.** Với `person == null`, kết quả của `#person?.address?.city ?: 'N/A'` là gì?  
**Đáp án:** `N/A`.

**Câu 2.** Nếu `person != null` nhưng `person.address == null`, `#person?.address.city` đã an toàn chưa?  
**Đáp án:** Chưa; dùng `#person?.address?.city`.

**Câu 3.** Vì sao `key = "#p0?.id"` không bảo đảm caching hoạt động khi ID null?  
**Đáp án:** Expression có thể trả null nhưng explicit cache key null không được Spring chấp nhận; cần tránh caching bằng condition hoặc sửa dữ liệu đầu vào.

**Câu 4.** Phương thức trả `Optional.empty()` và bạn không muốn lưu kết quả “không tìm thấy”. Viết `unless` nào?  
**Đáp án:** `unless = "#result == null"` trong cache evaluation context của Spring với Optional được hỗ trợ.

**Câu 5.** Với `#p0 == null`, `condition = "#p0 != null"` có bảo đảm Java method không chạy không?  
**Đáp án:** Không; nó chỉ bỏ qua cache. Method vẫn có thể chạy và phải tự xử lý null.

## Tài liệu chính thức

- [Spring Framework — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework — The Elvis Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html)
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)

**Ghi nhớ:** `?.` ngăn truy cập null tại đúng vị trí; `?:` cung cấp fallback có chủ đích; `condition` có thể ngăn áp dụng caching cho input thiếu; `unless` quyết định một kết quả sau khi tính có nên lưu. Cần bảo vệ cả tính đúng đắn của **cache key** và thời điểm có sẵn của các biến SpEL, không chỉ tránh exception.