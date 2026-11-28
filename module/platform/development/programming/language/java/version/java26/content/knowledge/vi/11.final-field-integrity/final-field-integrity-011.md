# Kiểm thử với chế độ deny để phát hiện phụ thuộc

JDK 26 bắt đầu cảnh báo khi mã Java dùng deep reflection để ghi vào một trường final sau khi đối tượng đã được khởi tạo. Mặc định, thao tác bất hợp pháp vẫn được phép thực hiện và JDK phát cảnh báo để hệ thống có thời gian tìm thư viện còn phụ thuộc vào hành vi này. Trong một bản phát hành tương lai, chế độ từ chối sẽ trở thành mặc định.

Cách kiểm tra chủ động là chạy toàn bộ ứng dụng và bộ kiểm thử với tùy chọn JVM **--illegal-final-field-mutation=deny**. Khi một module cố ghi vào trường final mà không được cấp quyền, Field.set() hoặc mutation method tương ứng sẽ ném IllegalAccessException. Lỗi này giúp tìm đúng dependency cần nâng cấp hoặc thay đổi trước khi hành vi mặc định của JDK trở nên nghiêm ngặt hơn.

Đây là thay đổi hành vi của JDK theo JEP 500 – *Prepare to Make Final Mean Final*, không phải preview feature. Không cần --enable-preview để sử dụng các tùy chọn kiểm thử trong bài.

## 1. Hiểu đúng phạm vi của JEP 500

Trong Java, trường final được khởi tạo trong constructor hoặc initializer và được kỳ vọng giữ nguyên giá trị sau khi đối tượng được tạo. Tuy nhiên, deep reflection trước đây có thể bỏ qua ranh giới đóng gói, truy cập trường private và thay đổi một số trường final của đối tượng đã khởi tạo.

JEP 500 bắt đầu siết hành vi đó trong JDK 26. Mục tiêu là bảo đảm tính toàn vẹn của trạng thái đối tượng: code khác có thể tin rằng giá trị final không bị thay đổi bất ngờ sau khi khởi tạo. Điều này hỗ trợ tính đúng đắn, an toàn và khả năng tối ưu của JVM.

Các mutation method được kiểm soát gồm:

- Field.set(Object, Object).
- Field.setBoolean(), setByte(), setChar(), setShort(), setInt(), setLong(), setFloat() và setDouble().
- MethodHandles.Lookup.unreflectSetter(Field) để lấy MethodHandle có quyền ghi vào trường final được phản chiếu.

Phạm vi bài học là việc ghi trường final thông qua reflection API và mutation method được JEP 500 quy định. Không suy rộng kết quả kiểm thử này thành bằng chứng rằng mọi cách truy cập bộ nhớ hoặc mọi native code đều đã bị kiểm soát bởi tùy chọn deny.

Một số trường vốn không thể được mở quyền ghi bằng cơ chế này:

- Trường static final.
- Trường final được khai báo trong record.
- Trường final được khai báo trong hidden class.

Với các loại trường này, không dùng --enable-final-field-mutation để tìm cách ghi. Hãy thiết kế dữ liệu qua constructor, factory hoặc API được lớp sở hữu công bố.

## 2. Phân biệt quyền truy cập reflection và quyền thay đổi final field

setAccessible(true) và quyền thay đổi trường final là hai điều kiện khác nhau.

Để một mutation method có thể ghi vào một trường final thông thường, các điều kiện chính phải được thỏa mãn:

1. setAccessible(true) đã thành công đối với đối tượng Field.
2. Module chứa code thực hiện mutation được cấp quyền thay đổi final field bằng --enable-final-field-mutation.
3. Lớp khai báo trường và caller thỏa một trong các quan hệ truy cập được API quy định: cùng module; hoặc trường và lớp khai báo là public trong package được export phù hợp; hoặc package khai báo trường được open cho caller module.
4. Trường là instance field trong lớp thông thường, không phải trường static, record hoặc hidden class.

Có thể hiểu bằng sơ đồ:

~~~text
Field.setAccessible(true) thành công
                 |
                 v
Caller module được bật final-field mutation?
                 |
          +------+------+
          |             |
         Không          Có
          |             |
          v             v
   Mutation bất hợp   Package / module của
   pháp               lớp khai báo cho phép
          |             |
          v             v
  --illegal-final-     Field có phải
  field-mutation      instance final field
  quyết định cách      trong class thường?
  xử lý                |
                 +-----+-----+
                 |           |
                Không        Có
                 |           |
                 v           v
              Từ chối     Mutation có thể
                          được phép
~~~

--add-opens chỉ xử lý khả năng truy cập sâu vào package. Nó không cấp quyền final-field mutation cho caller module. Vì vậy, thêm --add-opens mà không có --enable-final-field-mutation không làm cho một mutation bất hợp pháp trở thành hợp lệ.

Ngược lại, --enable-final-field-mutation cũng không tự mở một package đang bị module system đóng. Với named module, phải thiết kế opens phù hợp trong module descriptor hoặc cấu hình mở package cho đúng caller module.

Đừng nhầm IllegalAccessException với InaccessibleObjectException:

| Lỗi | Ý nghĩa thường gặp |
|---|---|
| InaccessibleObjectException tại setAccessible(true) | Module system không cho phép mở quyền truy cập sâu vào member/package |
| IllegalAccessException tại Field.set() | Không có quyền ghi vào trường final, hoặc trường thuộc loại không được phép thay đổi |
| IllegalArgumentException tại Field.set() | Đối tượng đích hoặc giá trị mới không tương thích với kiểu trường |

Phân biệt đúng điểm phát sinh lỗi giúp tìm nguyên nhân nhanh hơn. Bài kiểm thử deny tập trung vào trường hợp caller có thể lấy quyền truy cập reflection nhưng không được phép thay đổi final field.

## 3. Các chế độ kiểm soát trong JDK 26

Tùy chọn --illegal-final-field-mutation điều khiển cách JVM xử lý một lần ghi final field bị xem là bất hợp pháp:

| Chế độ | Hành vi | Mục đích |
|---|---|---|
| allow | Cho phép mutation bất hợp pháp, không cảnh báo | Biện pháp tạm thời khi đang điều tra |
| warn | Cho phép mutation và cảnh báo lần đầu theo từng caller module | Mặc định của JDK 26 và JDK 27 |
| debug | Cho phép mutation, in cảnh báo và stack trace cho từng lần mutation bất hợp pháp | Truy vết mọi call site |
| deny | Từ chối mutation bất hợp pháp bằng IllegalAccessException | Kiểm tra khả năng tương thích với chính sách tương lai |

Điểm quan trọng: deny chỉ từ chối mutation bất hợp pháp. Nếu caller module được cấp quyền rõ ràng bằng --enable-final-field-mutation và các điều kiện truy cập còn lại được thỏa mãn, mutation đó vẫn được cho phép.

JDK 26 và JDK 27 hiện vẫn dùng warn làm mặc định. Tài liệu JDK cho biết deny sẽ trở thành mặc định trong một bản phát hành tương lai; không nên tự giả định mốc release cụ thể khi chưa có thông báo chính thức.

Tùy chọn --illegal-final-field-mutation được dự kiến loại bỏ sau giai đoạn chuyển tiếp. Hãy dùng nó để tìm và sửa phụ thuộc, không biến allow thành cấu hình vận hành lâu dài.

## 4. Tạo chương trình nhỏ để xác nhận chế độ deny

Tạo file FinalFieldDenyProbe.java:

~~~java
import java.lang.reflect.Field;

public class FinalFieldDenyProbe {

    static final class Settings {
        private final String endpoint;

        Settings(String endpoint) {
            this.endpoint = endpoint;
        }

        String endpoint() {
            return endpoint;
        }
    }

    public static void main(String[] args) throws Exception {
        Settings settings = new Settings("https://before.example.test");

        Field field = Settings.class.getDeclaredField("endpoint");
        field.setAccessible(true);

        System.out.println("Before: " + settings.endpoint());

        field.set(settings, "https://after.example.test");

        System.out.println("After: " + settings.endpoint());
    }
}
~~~

Lớp Settings và caller nằm trong cùng unnamed module vì ví dụ chạy trên classpath. setAccessible(true) có thể thành công, nhưng unnamed module chưa được cấp quyền final-field mutation. Do đó, thao tác ghi là bất hợp pháp trong cấu hình mặc định.

Biên dịch bằng JDK 26:

~~~powershell
javac -d out src\FinalFieldDenyProbe.java
~~~

Chạy theo từng chế độ:

~~~powershell
# Mặc định của JDK 26: warn
java -cp out FinalFieldDenyProbe

# Chỉ định rõ warn
java --illegal-final-field-mutation=warn -cp out FinalFieldDenyProbe

# In stack trace cho mỗi lần mutation bất hợp pháp
java --illegal-final-field-mutation=debug -cp out FinalFieldDenyProbe

# Từ chối mutation bất hợp pháp
java --illegal-final-field-mutation=deny -cp out FinalFieldDenyProbe
~~~

Kết quả mong đợi:

| Lệnh | Kết quả |
|---|---|
| Mặc định hoặc warn | Giá trị được đổi và JVM phát cảnh báo |
| debug | Giá trị được đổi, cảnh báo kèm stack trace |
| deny | Field.set() ném IllegalAccessException; dòng in After không chạy |

Ví dụ cảnh báo có dạng:

~~~text
WARNING: Final field endpoint in class FinalFieldDenyProbe$Settings
has been mutated reflectively by class FinalFieldDenyProbe
in unnamed module ...
WARNING: Use --enable-final-field-mutation=ALL-UNNAMED to avoid a warning
WARNING: Mutating final fields will be blocked in a future release unless
final field mutation is enabled
~~~

JVM chỉ phát tối đa một cảnh báo ở chế độ warn cho mỗi caller module. Vì vậy, một lần chạy warn có thể không hiển thị tất cả trường bị thay đổi trong cùng module. Dùng debug để nhận cảnh báo và stack trace cho từng mutation bất hợp pháp.

### Kiểm tra tác động của allow-list

Chạy lại ví dụ với:

~~~powershell
java --illegal-final-field-mutation=deny --enable-final-field-mutation=ALL-UNNAMED -cp out FinalFieldDenyProbe
~~~

Trong ví dụ classpath, ALL-UNNAMED cấp quyền cho code trong unnamed modules. Vì package chứa Settings cũng truy cập được từ caller cùng module, mutation có thể thành công dù chế độ xử lý chung là deny.

Đây là phép thử để hiểu cơ chế allow-list, không phải cấu hình mặc định nên đưa vào production. Nếu dùng nó trong CI cho toàn bộ classpath, bạn đã cấp ngoại lệ rộng và có thể che khuất dependency cần sửa.

## 5. Kiểm tra các trường hợp module và package

Với ứng dụng modular, caller và lớp khai báo trường có thể thuộc hai module khác nhau. Ví dụ:

- com.example.model chứa lớp Settings và khai báo package.
- com.example.legacy chứa thư viện thực hiện reflection.

Nếu caller thuộc com.example.legacy, cấu hình mở package phải hướng tới caller đó. Có thể khai báo trong module chứa lớp đích:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.legacy;
}
~~~

Module caller cũng cần được cấp quyền mutation khi khởi chạy:

~~~powershell
java --enable-final-field-mutation=com.example.legacy --illegal-final-field-mutation=deny --module-path mods -m com.example.app/com.example.app.Main
~~~

Nếu dùng --add-opens thay cho opens trong module-info.java, package vẫn phải được mở đúng hướng:

~~~powershell
java --add-opens=com.example.model/com.example.model.internal=com.example.legacy --enable-final-field-mutation=com.example.legacy --illegal-final-field-mutation=deny --module-path mods -m com.example.app/com.example.app.Main
~~~

--enable-final-field-mutation chỉ định module thực hiện mutation, không phải module khai báo trường. Không dùng tên module đích thay cho caller module.

Đối với code chạy trên classpath, giá trị đặc biệt là ALL-UNNAMED. Với code trên module path, chỉ liệt kê các module caller thực sự cần quyền. Tránh cấp quyền cho mọi module nếu chỉ một thư viện cũ cần nó.

## 6. Chạy deny trên toàn bộ ứng dụng và dependency

Một chương trình probe chỉ xác nhận JVM đang xử lý đúng tùy chọn. Nó không phát hiện toàn bộ phụ thuộc của ứng dụng. Phải chạy các đường thực thi thật với đúng dependency graph.

Các khu vực cần kiểm tra:

- Khởi động ứng dụng và nạp cấu hình.
- Dependency injection, object mapping và binding cấu hình.
- ORM, persistence, proxy và hydration đối tượng.
- Serialization/deserialization và chuyển đổi dữ liệu.
- Framework JSON/XML, mapper và validation.
- Mocking, test fixture, test data builder và thư viện kiểm thử.
- Plugin, extension, module tải động và thư viện tích hợp.
- Luồng xử lý lỗi, phục hồi, reload cấu hình và các tác vụ nền.

Thư viện thường là nơi thực hiện deep reflection thay cho code nghiệp vụ. Một ứng dụng có thể vượt qua unit test nhưng vẫn thất bại khi chạy migration, xử lý một loại payload hiếm, khởi động plugin hoặc thực hiện một nhánh deserialization chưa được kiểm thử.

Thực hiện theo quy trình:

1. Chạy ứng dụng với JDK 26 hoặc JDK 27 hiện hành.
2. Chạy test suite với --illegal-final-field-mutation=deny.
3. Chạy integration test và end-to-end test với cùng cờ JVM.
4. Thực hiện các thao tác nghiệp vụ có dùng reflection hoặc framework mapping.
5. Ghi lại exception, class khai báo trường và thư viện caller.
6. Nâng cấp hoặc thay thế dependency gây mutation.
7. Chạy lại cùng bộ test ở chế độ deny.
8. Chỉ tạo allow-list nếu có một dependency thiết yếu chưa thể sửa và có lý do kỹ thuật được ghi nhận.

Không chỉ chạy một bài test đơn giản rồi kết luận ứng dụng đã sẵn sàng. Phải bao phủ các dependency và đường thực thi được triển khai thực tế.

## 7. Đưa chế độ deny vào Gradle và Maven

### Gradle

Đặt cờ cho JVM chạy test:

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs("--illegal-final-field-mutation=deny")
}
~~~

Nếu project có nhiều loại test task, kiểm tra tất cả task tương ứng, gồm unit test, integration test và test của từng module. Tác vụ chạy ứng dụng bằng JavaExec cũng cần cờ nếu muốn kiểm tra launcher đó:

~~~kotlin
tasks.withType<JavaExec>().configureEach {
    jvmArgs("--illegal-final-field-mutation=deny")
}
~~~

Cấu hình Test chỉ áp dụng cho JVM chạy test. Nó không tự thêm cờ vào JVM đang chạy Gradle daemon, JVM production hoặc tiến trình ứng dụng được khởi chạy ngoài Gradle.

### Maven Surefire và Failsafe

Với Maven Surefire, thêm cờ vào JVM fork dùng để chạy test:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--illegal-final-field-mutation=deny</argLine>
    </configuration>
</plugin>
~~~

Nếu project dùng JaCoCo hoặc plugin khác cũng cấu hình argLine, hãy ghép các tùy chọn hiện có thay vì ghi đè chúng. Integration test chạy qua Maven Failsafe cần cấu hình tương tự trong plugin đó.

Cờ này phải được truyền tới đúng JVM chạy test. Việc thêm nó vào compiler arguments của javac không có tác dụng vì đây là tùy chọn của lệnh java.

### Kiểm tra CI

Trong pipeline, ghi rõ:

- Nhà cung cấp và phiên bản JDK.
- Phiên bản Gradle wrapper hoặc Maven.
- JVM thực sự nhận --illegal-final-field-mutation=deny.
- Các test task và integration test đã chạy.
- Dependency nào được nâng cấp hoặc thay thế.
- Những ngoại lệ còn lại nếu có.

Chạy cùng cấu hình trên máy phát triển và CI. Không để IDE chạy test với deny trong khi pipeline hoặc test JVM khác vẫn dùng mặc định warn.

## 8. Dùng debug để tìm call site và JFR để lập danh sách mutation

### Chế độ debug

Khi chưa biết thư viện nào đang thay đổi final field, chạy ứng dụng với:

~~~powershell
java --illegal-final-field-mutation=debug -jar app.jar
~~~

JVM in cảnh báo và stack trace cho từng lần mutation bất hợp pháp. Stack trace giúp xác định:

- Trường bị thay đổi và lớp khai báo trường.
- Lớp thực hiện mutation.
- JAR hoặc module chứa caller.
- Đường gọi từ ứng dụng đến thư viện.

Đây là cách phù hợp để xác định dependency gây ra cảnh báo mà vẫn cho ứng dụng tiếp tục chạy trong quá trình điều tra. Sau khi tìm được nguyên nhân, chuyển lại sang deny để xác nhận việc sửa đã loại bỏ phụ thuộc.

### Java Flight Recorder

JDK 26 cung cấp sự kiện JFR jdk.FinalFieldMutation. Sự kiện có thể ghi nhận việc mutation final instance field qua deep reflection hoặc việc lấy MethodHandle có quyền ghi bằng Lookup.unreflectSetter(Field).

Có thể thực hiện một lần chạy phục vụ kiểm kê với quyền mutation được bật rõ ràng:

~~~powershell
java -XX:StartFlightRecording:filename=final-field-mutations.jfr --enable-final-field-mutation=ALL-UNNAMED -jar app.jar
~~~

Sau khi ứng dụng chạy qua các luồng cần kiểm tra, đọc sự kiện:

~~~powershell
jfr print --events jdk.FinalFieldMutation final-field-mutations.jfr
~~~

Sự kiện có thể cung cấp class khai báo trường, tên trường, thread và stack trace. Điều này hữu ích để lập danh sách thư viện cần cập nhật.

Đây là một lần chạy kiểm kê riêng: --enable-final-field-mutation=ALL-UNNAMED cấp quyền cho code trên classpath nên không còn kiểm tra chính sách từ chối đối với các module đó. Dùng debug hoặc deny trong lượt chạy riêng để kiểm tra hành vi bất hợp pháp. Khi mutation bị deny từ chối, không có thay đổi trường thành công để ghi thành sự kiện mutation.

Bảo vệ file JFR như dữ liệu chẩn đoán nội bộ. Stack trace có thể chứa tên package, đường dẫn và thông tin triển khai của ứng dụng.

## 9. Tìm kiếm dấu vết trong source code và dependency

Có thể tìm các API liên quan trong source code:

~~~powershell
rg -n --glob "*.java" "setAccessible|trySetAccessible|getDeclaredField|unreflectSetter" src test
rg -n --glob "*.java" "\.set(Boolean|Byte|Char|Short|Int|Long|Float|Double)?\s*\(" src test
~~~

Kết quả tìm kiếm chỉ là danh sách vị trí cần xem xét. Không phải mọi lần gọi setAccessible() đều thay đổi final field; thư viện có thể chỉ đọc trường. Tương tự, set() có thể là setter nghiệp vụ thông thường chứ không phải Field.set().

Đối với dependency bên ngoài:

- Kiểm tra stack trace ở chế độ debug để xác định JAR và phiên bản caller.
- Dùng dependency report của Gradle hoặc Maven để tìm dependency trực tiếp và bắc cầu.
- Kiểm tra release notes của thư viện để tìm hỗ trợ JDK 26 và thay đổi liên quan đến final-field mutation.
- Cập nhật lên phiên bản đã sửa hoặc thay thư viện bằng implementation không cần ghi final field.
- Chạy lại integration test với deny để xác nhận.

Không cố giải quyết bằng cách thêm --add-opens cho mọi package. Mở package chỉ giải quyết quyền truy cập sâu; nó không giải quyết phụ thuộc vào khả năng thay đổi final field.

## 10. Cách sửa các phụ thuộc thường gặp

| Nguồn phụ thuộc | Hướng xử lý |
|---|---|
| Dependency injection ghi vào private final field | Dùng constructor injection hoặc factory do lớp sở hữu cung cấp; nâng cấp framework nếu framework còn dùng mutation |
| Object mapper gán final field sau khi tạo đối tượng | Cấu hình constructor binding, creator hoặc factory được hỗ trợ |
| ORM nạp dữ liệu vào final field | Dùng mapping phù hợp với mô hình persistence và phiên bản ORM hỗ trợ; tránh tự ghi final field |
| Serialization framework tạo object bằng reflection | Nâng cấp framework và dùng cơ chế serialization/deserialization được hỗ trợ cho lớp |
| Mocking framework thay final field để tạo fixture | Nâng cấp framework; ưu tiên factory, constructor hoặc test double |
| Thư viện cấu hình sửa object sau khi khởi tạo | Dùng builder/mutable configuration trước khi tạo object bất biến |
| Thư viện cũ không còn được duy trì | Thay thế hoặc cô lập thành phần; chỉ cấp quyền mutation nếu chưa thể loại bỏ và có kiểm soát |

Ví dụ chuyển từ mutation sau khởi tạo sang constructor:

~~~java
import java.util.Objects;

// Thiết kế cũ, cần giá trị mặc định rồi bị thư viện sửa sau khi tạo:
final class LegacyServiceConfig {
    private final String endpoint;

    LegacyServiceConfig() {
        this.endpoint = "unset";
    }
}

// Thiết kế mới, truyền dữ liệu ngay khi khởi tạo:
final class ServiceConfig {
    private final String endpoint;

    ServiceConfig(String endpoint) {
        this.endpoint = Objects.requireNonNull(endpoint);
    }
}
~~~

Với thiết kế thứ hai, dependency injection hoặc object mapper truyền giá trị vào constructor/factory. Không cần thay đổi trạng thái của đối tượng sau khi khởi tạo.

Nếu cần thay đổi cấu hình trong vòng đời ứng dụng, đừng dùng reflection để sửa trường final. Hãy thay thế toàn bộ immutable config object bằng instance mới qua một điểm đồng bộ được thiết kế rõ ràng, hoặc dùng kiểu dữ liệu mutable có API và quy tắc đồng bộ phù hợp.

## 11. Khi nào cần allow-list final-field mutation?

Mục tiêu ưu tiên là loại bỏ phụ thuộc. Chỉ xem xét --enable-final-field-mutation khi:

- Dependency thực sự cần thiết cho hệ thống.
- Không có phiên bản thay thế tương thích.
- Không thể sửa hoặc thay dependency trong thời hạn hiện tại.
- Phạm vi trường và package đã được xác định.
- Rủi ro được chấp thuận và có kế hoạch loại bỏ ngoại lệ.

Ví dụ với một thư viện named module:

~~~powershell
java --enable-final-field-mutation=com.example.legacy --illegal-final-field-mutation=deny -jar app.jar
~~~

Trong ví dụ, chỉ module caller com.example.legacy được cấp quyền mutation. Package khai báo final field vẫn phải được open cho module caller theo quy tắc module system.

Với thư viện trên classpath:

~~~powershell
java --enable-final-field-mutation=ALL-UNNAMED --illegal-final-field-mutation=deny -jar app.jar
~~~

ALL-UNNAMED bao phủ code thuộc unnamed modules, nên phạm vi rộng hơn nhiều so với allow-list một named module. Tránh dùng cấu hình này nếu có thể modularize hoặc thay dependency. Không thêm nó chỉ để làm cho CI xanh trở lại.

Duy trì một hồ sơ ngoại lệ gồm module caller, package đích, dependency, lý do, người chịu trách nhiệm và thời hạn xem xét. Chạy deny cùng allow-list giúp hệ thống tiếp tục từ chối mọi module khác không được cấp quyền.

## 12. Ma trận kiểm thử cần lưu lại

| Ca kiểm thử | Cấu hình | Kết quả cần xác nhận |
|---|---|---|
| Probe với final instance field thông thường | Không bật mutation, warn | Mutation chạy và có cảnh báo |
| Probe với final instance field thông thường | Không bật mutation, debug | Mutation chạy, có cảnh báo và stack trace |
| Probe với final instance field thông thường | Không bật mutation, deny | Mutation thất bại với IllegalAccessException |
| Probe với caller module được bật | --enable-final-field-mutation và deny | Mutation có thể chạy nếu package/access conditions được thỏa mãn |
| Private field trong package của module khác không được open cho caller | Không có quyền deep reflection phù hợp | setAccessible(true) có thể thất bại trước bước mutation |
| Trường static final, record hoặc hidden class | Bất kỳ allow-list nào | Không dùng cơ chế này để ghi; kiểm tra API từ chối |
| Ứng dụng và toàn bộ test suite | deny, không allow-list rộng | Các luồng nghiệp vụ hoàn tất mà không phụ thuộc mutation bất hợp pháp |

Một lần chạy chỉ được xem là đạt khi các test nghiệp vụ và integration test đã chạy đủ phạm vi, không còn mutation bất hợp pháp bị deny từ chối, và các ngoại lệ còn lại (nếu có) đã được giới hạn rõ ràng.

## 13. Lỗi thường gặp khi kiểm thử

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| deny vẫn cho phép một mutation | Caller module đã được bật bằng --enable-final-field-mutation | Kiểm tra toàn bộ VM arguments, đặc biệt ALL-UNNAMED |
| setAccessible(true) ném InaccessibleObjectException | Package không được mở cho caller | Xem module descriptor và ranh giới đóng gói; không nhầm với final-field permission |
| Field.set() ném IllegalAccessException | Mutation không được cấp quyền hoặc trường không thể ghi | Xác định caller module, loại trường và các điều kiện API |
| Không thấy warning ở lần chạy thứ hai | warn chỉ phát tối đa một cảnh báo cho mỗi caller module trong tiến trình | Dùng debug để có stack trace cho từng lần mutation |
| Unit test qua nhưng production lỗi | Đường chạy hoặc dependency production chưa được kiểm thử | Chạy integration/end-to-end test với đúng dependency graph |
| JFR không có sự kiện khi chạy deny | Mutation bị chặn nên không có thao tác ghi thành công | Dùng debug để tìm lần gọi bị chặn; chạy JFR inventory riêng khi cần |
| Thêm --add-opens nhưng deny vẫn từ chối | Mở package không cấp quyền final-field mutation | Sửa dependency hoặc cấp quyền cho caller module trong trường hợp ngoại lệ được chấp thuận |
| Bật ALL-UNNAMED làm test qua | Toàn bộ code classpath đã được cấp quyền | Bỏ allow-list rộng và chạy lại deny để tìm phụ thuộc thực sự |

## 14. Bài thực hành

Thực hiện bằng JDK 26 hoặc JDK 27. Không cần preview flags.

1. Biên dịch FinalFieldDenyProbe và chạy ở chế độ mặc định. Ghi lại cảnh báo và giá trị sau mutation.
2. Chạy lại với --illegal-final-field-mutation=debug. Xác định caller class, module và stack trace.
3. Chạy với --illegal-final-field-mutation=deny. Xác nhận Field.set() ném IllegalAccessException.
4. Thử --enable-final-field-mutation=ALL-UNNAMED cùng deny. Giải thích vì sao caller trên classpath được phép mutation trong ví dụ.
5. Bỏ --enable-final-field-mutation nhưng thêm --add-opens trong một ví dụ named module. Xác nhận package mở không tự cấp quyền final-field mutation.
6. Tạo một test case cho record hoặc trường static final và xác nhận không thể dùng allow-list để thay đổi chúng.
7. Bật JFR trong một lượt kiểm kê riêng và đọc jdk.FinalFieldMutation để xác định field và call stack.
8. Chạy bộ test của ứng dụng với deny, bao gồm unit test, integration test và các đường khởi động/serialization/mapping quan trọng.
9. Nâng cấp dependency gây mutation hoặc thay bằng constructor/factory binding.
10. Chạy lại toàn bộ test với deny mà không cấp quyền rộng. Ghi lại các ngoại lệ còn lại và lý do nếu thật sự cần.

**Tiêu chí hoàn thành:** giải thích được sự khác nhau giữa quyền deep reflection và quyền final-field mutation; chạy được probe ở warn, debug và deny; nhận biết IllegalAccessException và InaccessibleObjectException; xác định được module/library gây mutation bằng stack trace hoặc JFR; cấu hình deny cho test JVM; loại bỏ dependency hoặc giới hạn allow-list ở mức nhỏ nhất; xác nhận ứng dụng chạy được trên JDK 26 và JDK 27 mà không dựa vào mutation bất hợp pháp.

## 15. Tài liệu tham khảo chính thức

- [JEP 500: Prepare to Make Final Mean Final](https://openjdk.org/jeps/500) — mục tiêu và lộ trình siết quyền thay đổi final field qua deep reflection.
- [Oracle JDK 26 Migration Guide: Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html) — các chế độ allow, warn, debug, deny, allow-list và cách xác định code gây mutation.
- [Java 26 Field API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html) — điều kiện setAccessible, khả năng ghi và các trường không thể thay đổi.
- [Java 26 Mutation Methods](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html) — danh sách mutation method và quy tắc cấp quyền.
- [Java 26 java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — cú pháp hai tùy chọn JVM --enable-final-field-mutation và --illegal-final-field-mutation.
- [Java 27 Migration Guide: Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/27/migrate/preparing-final-field-mutation-restrictions.html) — hướng dẫn tương ứng cho JDK 27.
- [Java 27 java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — xác nhận các chế độ và mặc định của JDK 27.
- [Inside Java: Avoiding Final Field Mutation](https://inside.java/2026/04/27/avoiding-final-field-mutation/) — các cách thiết kế thay thế cho reflection mutation.

JDK 26 và JDK 27 vẫn mặc định warn tại thời điểm viết bài. Dùng deny trong CI và môi trường thử nghiệm để phát hiện phụ thuộc sớm, sau đó sửa thư viện hoặc cấu trúc khởi tạo đối tượng. Không dựa vào việc một cờ tương thích tạm thời sẽ tồn tại trong các bản JDK tương lai.

