# Thông tin tên tham số và tùy chọn biên dịch `-parameters` trong Spring Cache SpEL

## 1. Vấn đề: vì sao `#isbn` có thể hoạt động ở máy này nhưng lỗi ở máy khác?

Khi khai báo bộ nhớ đệm bằng Spring Framework, ta thường chọn cache key bằng **Spring Expression Language (SpEL)**:

~~~java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findByIsbn(String isbn) {
    return repository.findByIsbn(isbn).orElseThrow();
}
~~~

Đây là **mã minh họa để tích hợp trong ứng dụng Spring**; `Book` và `repository` là thành phần nghiệp vụ, không phải chương trình tự chạy. Biểu thức `#isbn` cần Spring biết rằng đối số thứ nhất của phương thức tên là `isbn`. Nếu bytecode không giữ tên tham số ở dạng Java reflection đọc được, Spring có thể không gắn được tên `isbn` vào ngữ cảnh SpEL. Biểu thức khi đó không tạo được cache key dự kiến và lời gọi được cache có thể thất bại.

Vấn đề này khác với việc phương thức Java có thực sự nhận đối số hay không. JVM luôn biết **giá trị và vị trí** đối số để gọi phương thức. Nhưng tên trong source, như `isbn` hay `edition`, không bắt buộc phải được giữ trong metadata của file `.class`. **`javac -parameters`** yêu cầu compiler giữ thông tin đó để reflection và Spring có thể dùng.

Mục tiêu bài này: hiểu cơ chế tên tham số, kiểm chứng tác dụng của `-parameters`, sử dụng đúng `#name`/`#p0`/`#a0`/`#root.args[0]` trong SpEL của Spring Cache, cấu hình build và tìm lỗi khi deployment khác môi trường development.

## 2. Tên tham số đi từ source Java tới SpEL ra sao?

Xét chữ ký:

~~~java
public Book find(String isbn, int edition) {
    // Đọc sách theo ISBN và ấn bản...
}
~~~

Có hai loại thông tin cần phân biệt:

1. **Vị trí, kiểu và giá trị đối số:** đối số thứ nhất là `String`, đối số thứ hai là `int`; JVM vẫn truyền đúng hai giá trị dù không có `-parameters`.
2. **Tên do lập trình viên đặt:** `isbn` và `edition`. Muốn truy xuất bằng Java reflection, trình biên dịch phải lưu metadata tên tham số (attribute `MethodParameters` trong bytecode).

Spring sử dụng cơ chế tìm tên tham số (chẳng hạn `StandardReflectionParameterNameDiscoverer` cho Java) khi xây dựng ngữ cảnh đánh giá SpEL. Đường đi khái niệm:

~~~text
Java source: find(String isbn, int edition)
              |
              | javac -parameters
              v
.class: MethodParameters = isbn, edition
              |
              | Java reflection / Spring parameter-name discovery
              v
Spring Cache SpEL context:
    #isbn    = đối số thứ nhất
    #edition = đối số thứ hai
    #p0      = đối số thứ nhất (theo chỉ số)
    #p1      = đối số thứ hai  (theo chỉ số)
              |
              v
@Cacheable(key = "...") → cache key
~~~

Nếu compile không giữ tên, giá trị vẫn có thể được tham chiếu theo **vị trí** trong Spring Cache SpEL. Đây là điểm thực tế quan trọng nhất khi xây dựng bài học hoặc thư viện dùng lại.

### Các cách tham chiếu đối số trong cache SpEL

| Cú pháp SpEL | Truy cập | Cần `-parameters`? | Khi nào dùng |
|---|---|---|---|
| `#isbn` | Đối số có tên Java `isbn` | **Thông thường có** với mã Java và Spring hiện đại | Rõ nghĩa, dễ đọc, phù hợp codebase cấu hình giữ tên tham số |
| `#edition` | Đối số có tên Java `edition` | **Thông thường có** | Điều kiện/key dựa trên đối số thứ hai theo tên |
| `#p0`, `#p1` | Đối số chỉ số 0, 1 | Không | Muốn tránh phụ thuộc tên trong bytecode |
| `#a0`, `#a1` | Bí danh theo chỉ số 0, 1 | Không | Tương đương `#p0` và `#p1` |
| `#root.args[0]`, `#root.args[1]` | Mảng đối số trong root object | Không | Muốn chỉ rõ truy cập qua context root |

**Chỉ số bắt đầu từ 0.** Với `find(String isbn, int edition)`: `#p0` và `#a0` và `#root.args[0]` cùng trỏ tới giá trị `isbn`; `#p1` trỏ tới `edition`. `#p0` là tên biến SpEL do Spring cấp; đừng nhầm với chuỗi tên mà Java reflection có thể hiển thị là `arg0` khi thiếu metadata. `#arg0` không phải cú pháp fallback được Spring Cache bảo đảm như `#p0`.

**Điều kiện sử dụng tên:** ở đây nói về đối số **phương thức đang được Spring Cache intercept**, không phải mọi biến cục bộ trong thân phương thức. Tên biến local như `String normalized = ...` không tự thành biến `#normalized` trong expression của `@Cacheable`.

## 3. Thử nghiệm Java 17 độc lập: có và không có `-parameters`

Để tách riêng cơ chế Java khỏi Spring, tạo tệp **`ParameterNamesDemo.java`** sau. Chỉ dùng JDK 17+, không cần Maven/Gradle hay dependency nào:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterNamesDemo {
    public String load(String isbn, int edition) {
        return isbn + ":" + edition;
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Method method = ParameterNamesDemo.class
                .getDeclaredMethod("load", String.class, int.class);
        Parameter[] parameters = method.getParameters();

        for (int i = 0; i < parameters.length; i++) {
            System.out.printf("p%d: name=%s, present=%s%n",
                    i, parameters[i].getName(), parameters[i].isNamePresent());
        }
    }
}
~~~

### Lần 1: biên dịch không bật giữ tên

~~~bash
javac --release 17 ParameterNamesDemo.java
java ParameterNamesDemo
~~~

Stdout (với `javac` chuẩn, không bật `-parameters` ở nơi khác):

~~~text
p0: name=arg0, present=false
p1: name=arg1, present=false
~~~

`Parameter.getName()` trả về tên tổng hợp `arg0` và `arg1`; `Parameter.isNamePresent()` là `false`. Đây không phải hai tên mà mã nguồn khai báo.

### Lần 2: chỉ bật thông tin debug

~~~bash
javac --release 17 -g ParameterNamesDemo.java
java ParameterNamesDemo
~~~

Stdout vẫn là:

~~~text
p0: name=arg0, present=false
p1: name=arg1, present=false
~~~

`-g` tạo thông tin hỗ trợ debug, có thể gồm bảng biến cục bộ, nhưng **không thay thế `-parameters`** trong việc cung cấp tên cho Java reflection.

### Lần 3: bật metadata tên tham số

~~~bash
javac --release 17 -parameters ParameterNamesDemo.java
java ParameterNamesDemo
~~~

Stdout:

~~~text
p0: name=isbn, present=true
p1: name=edition, present=true
~~~

Ở lần này, tên trong source được giữ để `Method.getParameters()` đọc. Câu lệnh thứ ba biên dịch lại cùng tệp `.class`; không được chạy bằng một bản `.class` cũ còn nằm trước trên classpath. Có thể kiểm tra bytecode bằng lệnh:

~~~bash
javap -v ParameterNamesDemo
~~~

Trong phần phương thức `load` của bản biên dịch có `-parameters`, tìm attribute **`MethodParameters`** với các tên `isbn`, `edition`. Nếu thấy phần `LocalVariableTable` do `-g` tạo, cần hiểu đó là **metadata khác**. Ba trường hợp trên đã được đối chiếu với Java 17 target; khác biệt nằm ở metadata, không nằm ở giá trị trả về của `load`.

## 4. Tại sao Spring Framework 6.1+ đặc biệt cần chú ý?

Ở các bản Spring cũ, có thời điểm framework hỗ trợ dò tên tham số Java từ thông tin debug `LocalVariableTable` khi metadata chuẩn không có. **Spring Framework 6.1 đã loại bỏ `LocalVariableTableParameterNameDiscoverer`** và không tiếp tục dựa vào đọc bảng biến cục bộ để suy luận tên như cách cũ. Vì vậy, việc code “trước đây chạy được với `-g`” không phải bằng chứng rằng nó còn chạy đúng trên Spring 6.1+.

Với các biểu thức cache dựa trên **tên** như `key = "#isbn"`, hướng ổn định cho mã Java là bật **`-parameters`** khi build source tương ứng. Không nên suy luận rằng bật debug mode, tạo source map, dùng `--release 17` hoặc chạy JDK 17+ là đủ.

Điều này không có nghĩa mọi biểu thức `@Cacheable` đều cần `-parameters`. Nếu dùng **default key generator**, `#p0`, `#a0` hoặc `#root.args[0]`, Spring đã có giá trị đối số theo vị trí mà không cần tên từ reflection.

## 5. Áp dụng vào các annotation cache

### 5.1. `@Cacheable` và key theo tên

~~~java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findByIsbn(String isbn) {
    return repository.findByIsbn(isbn).orElseThrow();
}
~~~

Khi phương thức được gọi qua cache interception, Spring đánh giá `#isbn` thành đối số `String`, dùng làm key để tìm giá trị trong cache `books`. Mẫu này dễ đọc, nhưng phải chắc rằng runtime method có metadata tên tham số phù hợp.

Ba cách viết thay thế **độc lập** cho cùng tham số đầu tiên:

~~~java
// Mỗi annotation dưới đây là MỘT phương án, không đặt cùng lúc.
@Cacheable(cacheNames = "books", key = "#p0")
// hoặc:
@Cacheable(cacheNames = "books", key = "#a0")
// hoặc:
@Cacheable(cacheNames = "books", key = "#root.args[0]")
~~~

Chúng không cần metadata tên Java. Đổi lại, nếu về sau thay đổi **thứ tự đối số**, chỉ số `0` có thể trỏ sang giá trị khác; phải sửa và kiểm thử lại expression.

### 5.2. Nhiều tham số: tên đủ chưa, key đã đúng chưa?

Giả sử service đọc sách theo tenant và ISBN:

~~~java
@Cacheable(cacheNames = "tenantBooks",
           key = "#tenantId + ':' + #isbn")
public Book find(String tenantId, String isbn) {
    return repository.findForTenant(tenantId, isbn).orElseThrow();
}
~~~

Cả `#tenantId` và `#isbn` đều cần tên tham số được cung cấp đúng. Hơn nữa, biểu thức nối chuỗi cần có **quy tắc mã hóa không nhập nhằng**: nếu giá trị đầu vào có thể chứa dấu `:`, hai cặp đối số khác nhau có thể tạo key giống nhau. Khi cache key cần gồm **đầy đủ mọi đối số**, có thể đơn giản hơn bằng cách bỏ hẳn thuộc tính `key`:

~~~java
@Cacheable(cacheNames = "tenantBooks")
public Book find(String tenantId, String isbn) {
    return repository.findForTenant(tenantId, isbn).orElseThrow();
}
~~~

Mặc định, Spring dùng một `SimpleKey` chứa cả hai đối số khi phương thức có nhiều đối số. Với phương thức chỉ có **một** đối số, key mặc định là chính giá trị đối số đó (khi tương thích theo hợp đồng của key generator); với **không** đối số, key là `SimpleKey.EMPTY`. Đây là lựa chọn không phụ thuộc metadata tên tham số, nhưng vẫn phải kiểm tra `equals()` và `hashCode()` của đối số nếu là object tự tạo.

**Đừng dùng `key = "#p0"` chỉ để chữa lỗi thiếu tên** khi tham số thứ hai vẫn ảnh hưởng kết quả. Khi đó request của hai tenant, phiên bản, ngôn ngữ hoặc filter khác nhau có thể trùng key và nhận sai dữ liệu.

### 5.3. `condition` và `unless` có thời điểm đánh giá khác nhau

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#isbn",
    condition = "#isbn != null && !#isbn.isBlank()",
    unless = "#result == null"
)
public Book findByIsbn(String isbn) {
    return repository.findByIsbn(isbn).orElse(null);
}
~~~

- `key` dùng biểu thức để tính key cho cache; `condition` xác định **trước khi gọi phương thức** liệu cơ chế cache có được áp dụng hay không.
- `unless` được đánh giá **sau khi phương thức thực sự được gọi**, dùng `#result` để từ chối đưa kết quả vào cache.
- `#result` **không có sẵn trong `key` của `@Cacheable`** hay `condition` trước khi có kết quả. Nó được hỗ trợ ở `unless`, các biểu thức key của `@CachePut` và `@CacheEvict` sau khi gọi (với `beforeInvocation = false`).
- Nếu phương thức trả về `Optional<T>`, `#result` trong cache expression tham chiếu tới giá trị nghiệp vụ được unwrap theo quy tắc Spring Cache; có thể là `null`. Cần dùng toán tử null-safe khi truy cập thuộc tính.

Ví dụ trên vẫn cần `-parameters` vì `#isbn` xuất hiện trong `key` và `condition`. Nếu không chắc metadata, chuyển nhất quán sang `#p0` tại **mọi vị trí** tham chiếu đối số:

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
~~~

Các đoạn annotation ở mục này là **ví dụ tích hợp Spring**, không tự biên dịch một mình: cần `@EnableCaching`, cache manager/provider, bean service và class/repository tương ứng.

### 5.4. `@CacheEvict` và `@CachePut` cũng có thể gặp lỗi tên

~~~java
@CacheEvict(cacheNames = "books", key = "#isbn")
public void remove(String isbn) {
    repository.deleteByIsbn(isbn);
}
~~~

Sau khi xóa dữ liệu thành công, Spring cần xác định key để evict. Nếu tên `isbn` không được giữ, expression có thể không tạo được key hợp lệ. Có thể chuyển thành `key = "#p0"` nếu phương thức chỉ có đối số đó; điều quan trọng là **key evict phải khớp với key cache của phương thức đọc**.

Với `@CachePut`, phương thức vẫn chạy và kết quả được đưa vào cache; `#result` được dùng trong ngữ cảnh thích hợp sau khi có kết quả, còn `#p0` vẫn tham chiếu đối số theo vị trí. Việc có tên đối số trong SpEL **không** làm annotation tự hoạt động: phải có Spring caching được bật và lời gọi đi qua đúng cơ chế interception (trong proxy mode, tự gọi `this.method()` cùng bean thường bỏ qua proxy).

## 6. Bật `-parameters` trong quy trình build

### 6.1. Gọi `javac` trực tiếp

~~~bash
javac --release 17 -parameters MyService.java
~~~

`--release 17` chọn API và phiên bản class tương thích Java 17; **`-parameters`** là tùy chọn độc lập để giữ tên. Tên đúng là `-parameters` (số nhiều). Nếu biên dịch lại, phải chắc ứng dụng chạy class/JAR vừa được biên dịch và không bị một class cũ trên classpath che khuất.

### 6.2. Gradle với `build.gradle` (Groovy DSL)

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
~~~

Cấu hình này áp dụng cho các task `JavaCompile` trong project mà đoạn cấu hình được đặt vào, thường bao gồm source production và test trong project đó. Nếu sử dụng nhiều subproject/module, phải áp dụng cấu hình tới **các module chứa method được cache**; đừng mặc nhiên cho rằng cấu hình của một module tự truyền sang mọi module khác.

### 6.3. Gradle với `build.gradle.kts` (Kotlin DSL)

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Cơ chế tác động đến `javac` tương tự Groovy DSL. Sau khi sửa build script, **compile lại bytecode** và kiểm tra artifact thực sự được đóng gói/deploy, thay vì chỉ khởi động lại ứng dụng từ class cũ.

### 6.4. Maven Compiler Plugin

Trong `pom.xml`, cấu hình cho plugin biên dịch Java:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Thuộc tính cấu hình tương ứng là `maven.compiler.parameters`; trong project dùng Maven Compiler Plugin phù hợp có thể khai báo:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

Đừng thêm đoạn `build` thứ hai nếu POM đã có sẵn: chỉ hợp nhất cấu hình vào POM hiện hành. Cũng đừng mặc định mọi phiên bản plugin/framework đã bật cờ này hộ bạn; **kiểm tra bytecode đầu ra** là cách xác nhận trực tiếp nhất.

## 7. Chẩn đoán khi expression `#name` không hoạt động

Một quy trình có thể áp dụng cho lỗi cache SpEL:

1. **Xác định expression đang chạy:** kiểm tra `key`, `condition`, `unless` trong `@Cacheable`, `@CachePut`, `@CacheEvict`. Chẳng hạn `key="#isbn"` phải tương ứng tên đối số đúng của method.
2. **Kiểm tra compiler metadata trên class được chạy:** dùng reflection `Parameter.isNamePresent()` và `getName()` như ví dụ; hoặc `javap -v` để kiểm tra `MethodParameters`. Kết quả `arg0/false` là dấu hiệu thiếu metadata tên.
3. **Kiểm tra lệnh build và bản deploy:** flag có áp dụng đúng module/source set, có compile lại sạch phần cần thiết, JAR/container mới có được triển khai hay không. Một dependency JAR đã biên dịch thiếu flag không được sửa chỉ bằng việc bật flag cho project đang sử dụng nó.
4. **Kiểm tra biến thể không phụ thuộc tên:** tạm thay `#isbn` bằng `#p0` (chỉ khi cùng ý nghĩa key). Nếu cách này hoạt động, vấn đề nhiều khả năng nằm ở việc khám phá tên tham số.
5. **Kiểm tra correctness của key và annotation:** việc tạo được key không chứng minh cache đúng. Với nhiều đối số, phải bao phủ mọi tham số có ảnh hưởng đến kết quả, gồm tenant/phân quyền khi thích hợp.
6. **Kiểm tra cache interception:** nếu không thấy hit, xác nhận có `@EnableCaching`, `CacheManager` phù hợp và invocation đi qua Spring proxy. Đây là vấn đề khác với thiếu tên tham số.

Triệu chứng có thể gặp khi biểu thức trả về key `null` là lỗi kiểu **“Null key returned for cache operation”**; nếu expression truy cập thuộc tính/phương thức trên đối tượng không xác định, có thể phát sinh lỗi đánh giá SpEL khác. Không nên dựa vào đúng từng chữ của exception giữa các phiên bản. Đọc cấu hình expression và kiểm tra metadata mới xác định nguyên nhân.

### Bảng quyết định khi sửa

| Tình huống | Cách xử lý phù hợp | Rủi ro còn lại |
|---|---|---|
| Muốn viết `#isbn` để dễ đọc | Bật `-parameters` và compile lại method chứa tham số | Đổi tên tham số mà quên sửa expression |
| Không kiểm soát cách JAR bên thứ ba được biên dịch | Cân nhắc `#p0`/`#a0`/`#root.args[0]` trong code có thể sửa | Đổi thứ tự đối số có thể làm key sai |
| Dùng hết mọi đối số để định danh kết quả | Cân nhắc key generator mặc định | Phải có `equals/hashCode` phù hợp; không bỏ qua tham số phi nghiệp vụ có thể gây key phân mảnh |
| Đã có `-g` nhưng tên không tìm được | Dùng `-parameters`; kiểm tra `MethodParameters` | Debug info không thay thế Java reflection metadata |
| Cache có key đúng nhưng không có hit | Kiểm tra proxy, `@EnableCaching`, cache manager và lần gọi thực tế | Lỗi có thể không liên quan tham số |
| Triển khai nhiều module, chỉ lỗi tại môi trường chạy | Kiểm tra class/JAR và compile task của module thật sự được load | Artifact cũ hoặc bản biên dịch khác nhau |

## 8. Những hiểu lầm và lỗi thiết kế cần tránh

- **“Tên trong source Java luôn có trong `.class`.”** Sai. Mã nguồn và metadata reflection có hợp đồng khác nhau; cần xác minh tên được giữ.
- **“`-g` tương đương `-parameters`.”** Sai. Spring 6.1+ không còn dùng cơ chế dò tên từ `LocalVariableTable` như trước.
- **“`-parameters` sửa mọi vấn đề Spring Cache.”** Sai. Nó chỉ cung cấp tên cho một nhóm tình huống; cache manager, self-invocation, transaction, TTL, eviction và key correctness vẫn là các vấn đề độc lập.
- **“Không có `-parameters` thì không thể dùng `@Cacheable`.”** Sai. Key mặc định và cú pháp theo vị trí vẫn dùng được.
- **“`#p0` an toàn trong mọi lần refactor.”** Sai. Đổi thứ tự tham số là thay đổi ý nghĩa của chỉ số; nếu thiếu đối số tenant/version, còn có nguy cơ dùng chéo dữ liệu.
- **“`#result` luôn có sẵn.”** Sai. Trong `@Cacheable`, nó được dùng cho `unless` sau khi có kết quả, không phải `key` hoặc `condition` trước lúc gọi.
- **“Chỉ cần cài flag ở project chạy chính.”** Sai trong nhiều hệ multi-module. Quan trọng là **class có phương thức được intercept** đã biên dịch với metadata thích hợp.
- **“Có `arg0` trong reflection nghĩa là viết `#arg0` được.”** Không nên suy luận như vậy. Dùng các alias được Spring Cache hỗ trợ chính thức: `#p0`, `#a0` hoặc `#root.args[0]`.
- **“Đổi tên `isbn` thành `code` không ảnh hưởng gì.”** Với biểu thức gắn tên `#isbn`, refactor nguồn cần cập nhật expression và kiểm thử behavior; compiler không tự sửa chuỗi SpEL trong annotation.

## 9. Tự kiểm tra

**Câu 1.** Phương thức `Book find(String isbn, int edition)` được compile không có `-parameters`. Những expression nào vẫn có thể truy cập đối số thứ hai: `#edition`, `#p1`, `#a1`, `#root.args[1]`?

**Câu 2.** Lệnh `javac --release 17 -g Demo.java` đã giúp Java reflection nhận tên `isbn` chưa? Nếu chưa, cần thêm cờ nào?

**Câu 3.** `@Cacheable(key="#p0")` áp dụng cho phương thức `find(String isbn, String tenantId)`. Nếu dữ liệu khác nhau theo tenant, cache key này có rủi ro gì?

**Câu 4.** Vì sao `@Cacheable(key="#result.id")` không phải cách chọn key đúng theo thời điểm thực thi của annotation?

**Câu 5.** Sau khi thêm `-parameters` vào Gradle mà ứng dụng vẫn không thấy tên, nên kiểm tra gì trước khi kết luận Spring có lỗi?

**Đáp án và giải thích:**

1. `#p1`, `#a1`, `#root.args[1]` truy cập vị trí thứ hai; `#edition` phụ thuộc tên được cung cấp.
2. Chưa. `-g` phục vụ debug; thêm `-parameters` và biên dịch lại class.
3. Hai tenant có cùng ISBN sẽ dùng chung key, có nguy cơ nhận dữ liệu của tenant khác; cần key chứa đủ ngữ cảnh hoặc dùng generator mặc định phù hợp.
4. Cache key của `@Cacheable` phải được biết khi tra cứu cache **trước** lúc quyết định có chạy method hay không; `#result` chỉ tồn tại sau khi method đã chạy trong ngữ cảnh hỗ trợ.
5. Xem compile task của module chứa method, class/JAR thực sự được deploy, `MethodParameters` trong bytecode, cache proxy/configuration và expression được gọi.

## 10. Tài liệu tham khảo

- Spring Framework — Declarative Annotation-based Caching và bảng SpEL evaluation context: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.1 Release Notes — Parameter Name Retention, loại bỏ `LocalVariableTableParameterNameDiscoverer`: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes
- Oracle JDK — `javac`: định nghĩa `-parameters`, `-g` và `--release`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Gradle Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Maven Compiler Plugin — `parameters`: https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html

**Điểm cần nhớ:** Trong Spring Cache SpEL, `#isbn` cần tên tham số Java được nhận diện đúng; bật `javac -parameters` cho class chứa method là cách ổn định với Spring Framework 6.1+. Các biến `#p0`, `#a0` và `#root.args[0]` dùng **vị trí đối số**, không phụ thuộc metadata tên. Dù chọn cách nào, cache key vẫn phải bao hàm đúng những đầu vào quyết định kết quả.