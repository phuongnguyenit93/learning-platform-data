# Đối chiếu nullability 3.x với JSpecify ở dòng 4.x

## 1. Chuyển phiên bản là dịp đối chiếu lại hợp đồng null

Trong chương **Phiên bản và AOT** của module **SPRING_DATA_COMMONS**, chuyển từ dòng 3.x sang 4.x không chỉ là thay import của một annotation tên Nullable.

Điều cần giữ là hợp đồng:

- Đối số nào được phép null?
- Không có kết quả thì trả null, Optional.empty, collection rỗng hay báo lỗi?
- Một collection không null có được chứa phần tử null không?
- Nullability của mảng áp dụng cho mảng hay từng phần tử?
- Kotlin nhìn thấy kiểu nullable, non-null hay platform type?
- Kiểm tra nào xảy ra ở compiler/tooling, ở repository proxy và ở database?

Spring Data 3.x thường trình bày nullability repository bằng các annotation `org.springframework.lang`, dựa trên cơ chế JSR-305. Spring Framework 7 và Spring Data 4 chuyển trọng tâm sang JSpecify; các annotation null-safety cũ của Spring được deprecate từ Framework 7. [Hướng dẫn null-safety của Spring Framework](https://docs.spring.io/spring-framework/reference/core/null-safety.html).

Bài này đối chiếu quy ước 3.x với hướng dùng JSpecify ở 4.x. Khi nói về implementation runtime, cần đối chiếu đúng phiên bản cụ thể; không suy rằng mọi bản 3.x hoặc mọi bản 4.x có toàn bộ chi tiết giống nhau.

## 2. Ba lớp phải được phân biệt

| Lớp | Ví dụ | Ai thực thi? |
| --- | --- | --- |
| Hợp đồng nullness của API | Parameter không null, phần tử list có thể null | Người đọc, IDE, Kotlin compiler hoặc nullness checker |
| Kiểm tra tại lời gọi repository | Chặn đối số null, từ chối kết quả null ở API bắt buộc | Hạ tầng proxy/validator khi được áp dụng |
| Ràng buộc dữ liệu | Column NOT NULL, validator document, invariant entity | Store, mapping hoặc code nghiệp vụ tương ứng |

Một annotation JSpecify không tự thêm câu lệnh kiểm tra null vào mọi method Java. Một cột NOT NULL cũng không tự làm Kotlin hiểu chính xác kiểu trả về của Java API.

AOT là một trục khác nữa: xử lý cấu hình ứng dụng sớm không thay thế các hợp đồng nullness và kiểm tra dữ liệu.

~~~mermaid
flowchart TD
    A["Khai báo hợp đồng nullness"] --> B["Tooling hoặc compiler phân tích"]
    A --> C["Repository infrastructure đọc metadata nếu hỗ trợ"]
    B --> D["Phát hiện lời gọi hoặc implementation không phù hợp"]
    C --> E["Kiểm tra tại runtime theo phạm vi thực tế"]
    F["Schema và dữ liệu store"] --> G["Kiểm tra mapping và ràng buộc dữ liệu"]
    E --> H["Hành vi ứng dụng được kiểm chứng"]
    G --> H
~~~

## 3. Quy ước phổ biến ở Spring Data 3.x

### 3.1. NonNullApi là mặc định cho parameter và return value

Ví dụ nội dung một package-info.java trong mã 3.x:

~~~java
@org.springframework.lang.NonNullApi
package example.accounts;
~~~

`@NonNullApi` định nghĩa mặc định non-null cho parameter và return value trong package. Nó không phải annotation mặc định cho mọi generic type-use hoặc mọi field. [NonNullApi của Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/lang/NonNullApi.html).

Nếu dùng `@NonNullFields`, đó là một khai báo riêng cho field trong package. Không gộp hai annotation thành một ý nghĩa chỉ vì tên đều bắt đầu bằng NonNull. [NonNullFields API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/lang/NonNullFields.html).

### 3.2. Nullable của Spring là annotation trên declaration

Ví dụ repository 3.x trong package đã có NonNullApi:

~~~java
package example.accounts;

import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.Repository;
import org.springframework.lang.Nullable;

public interface AccountRepository extends Repository<Account, Long> {

    Account getByUsername(String username);

    @Nullable
    Account findByEmail(@Nullable String email);

    Optional<Account> findOptionalByUsername(String username);

    List<Account> findByEnabledTrue();
}
~~~

`Account` là domain type của ứng dụng, có các property username, email và enabled, được map theo module store đang dùng. Các public type/snippet trong bài cần đặt trong những file phù hợp khi đưa vào dự án.

Ở đây:

- `getByUsername` diễn đạt kết quả bắt buộc và đối số không null theo default.
- `findByEmail` khai báo cho phép cả đối số email null lẫn kết quả null.
- `findOptionalByUsername` dùng empty Optional để biểu diễn không có kết quả.
- `findByEnabledTrue` dùng collection rỗng khi không có phần tử.

Spring `@Nullable` có target method, parameter và field; nó không cung cấp cùng semantics type-use như JSpecify. [Nullable của Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/lang/Nullable.html).

### 3.3. Kết quả không tồn tại và kết quả bắt buộc

Với cấu hình non-null repository phù hợp, tài liệu dòng 3.5 mô tả query trả entity bắt buộc sẽ báo lỗi khi không có kết quả; query nullable trả null; query Optional trả Optional.empty. Collection/wrapper/stream được hạ tầng hỗ trợ dùng biểu diễn rỗng thay cho null. [Null handling của Spring Data Commons 3.5](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/null-handling.html).

Nullability của parameter chỉ nói API có chấp nhận giá trị null. Nó không nói query sẽ bỏ qua predicate, tìm field null hay chuyển null thành một giá trị mặc định. Semantics đó phải được kiểm tra theo module/query cụ thể.

Ví dụ, “email null là không áp dụng bộ lọc” là một quyết định nghiệp vụ riêng. Đừng gắn Nullable vào parameter rồi mặc định query derivation có đúng ý nghĩa đó.

## 4. Hướng khai báo ở Spring Data 4.x với JSpecify

### 4.1. NullMarked đặt mặc định theo một scope

Ví dụ package-info.java cho package repository đã được đối chiếu:

~~~java
@NullMarked
package example.accounts;

import org.jspecify.annotations.NullMarked;
~~~

`@NullMarked` xác định một null-marked context; các type usage thông thường trong scope được hiểu là không chứa null nếu không có khai báo khác. Nó có thể dùng ở những scope được JSpecify quy định như package hoặc type. [NullMarked API](https://jspecify.dev/docs/api/org/jspecify/annotations/NullMarked.html).

Quan trọng: package Java không phải một cây scope kế thừa theo tên. Đặt NullMarked trên `example.accounts` không tự đánh dấu `example.accounts.internal`. Cần kiểm tra từng package hoặc chọn scope khác phù hợp. [JSpecify user guide về scope](https://jspecify.dev/docs/user-guide/).

### 4.2. Nullable áp dụng lên type usage

Repository tương ứng ở dòng 4.x:

~~~java
package example.accounts;

import java.util.List;
import java.util.Optional;

import org.jspecify.annotations.Nullable;
import org.springframework.data.repository.Repository;

public interface AccountRepository extends Repository<Account, Long> {

    Account getByUsername(String username);

    @Nullable Account findByEmail(@Nullable String email);

    Optional<Account> findOptionalByUsername(String username);

    List<Account> findByEnabledTrue();
}
~~~

Đây là phiên bản thay thế cho interface 3.x phía trước, không phải interface đăng ký song song cùng tên.

Điểm khác nằm ở `org.jspecify.annotations.Nullable` và default scope của JSpecify. Annotation này có target TYPE_USE: nó đánh dấu lần sử dụng kiểu cụ thể có thể bao gồm null. [JSpecify Nullable API](https://jspecify.dev/docs/api/org/jspecify/annotations/Nullable.html).

Spring Data 4 mô tả JSpecify như cách biểu đạt nullability cho repository cùng hướng tích hợp của Framework 7. [Null handling ở dòng Spring Data 4](https://docs.spring.io/spring-data/commons/reference/repositories/null-handling.html).

### 4.3. Bảng đối chiếu

| Mục tiêu | Cách quen thuộc trong 3.x | Cách JSpecify trong 4.x |
| --- | --- | --- |
| Default cho parameter/return | NonNullApi ở package | NullMarked ở scope phù hợp |
| Khai báo nullable | Spring Nullable trên declaration | JSpecify Nullable trên type usage |
| Khai báo non-null tường minh | Spring NonNull | JSpecify NonNull khi cần |
| Mặc định cho field | NonNullFields riêng | Type usage của field trong null-marked context |
| Nullability phần tử generic | Không biểu đạt đầy đủ bằng nhóm annotation Spring cũ | Có thể ghi ở type argument |
| Phân biệt mảng và phần tử | Declaration annotation không có cùng độ chính xác | Đặt type-use đúng vị trí |
| Vùng chưa được phân loại | Thường là code chưa có default/annotation | Null-unmarked context, có thể khai báo NullUnmarked |

Bảng này là đối chiếu ý nghĩa, không phải danh sách find-and-replace an toàn. Đặc biệt, một NullMarked mới có thể làm hợp đồng của các field/type argument rõ và chặt hơn phạm vi NonNullApi cũ.

### 4.4. Không cần ghi NonNull ở mọi vị trí

Trong scope NullMarked, một type cụ thể thông thường như String đã có default non-null. Thêm NonNull ở mọi parameter và return value thường tạo nhiễu.

NonNull vẫn có vai trò trong một số trường hợp như khai báo tường minh ở scope chưa được đánh dấu hoặc các tình huống type variable nâng cao. [JSpecify NonNull API](https://jspecify.dev/docs/api/org/jspecify/annotations/NonNull.html).

Không suy rằng mọi type variable T đều được hiểu y hệt một type cụ thể String; phần generic cần xét upper bound và type argument.

## 5. Collection: container và phần tử là hai hợp đồng

Trong một scope NullMarked, các chữ ký sau khác nhau:

~~~java
import java.util.List;
import org.jspecify.annotations.Nullable;

List<Account> requiredAccounts();

@Nullable List<Account> optionalListReference();

List<@Nullable Account> accountsWithPossibleNullEntries();

@Nullable List<@Nullable Account> nullableListWithNullableEntries();
~~~

Đây là ví dụ API Java tổng quát để đọc type-use, không phải khuyến nghị query repository trả collection null.

| Chữ ký | List có thể null? | Phần tử có thể null? |
| --- | --- | --- |
| List<Account> | Không | Không |
| @Nullable List<Account> | Có | Không |
| List<@Nullable Account> | Không | Có |
| @Nullable List<@Nullable Account> | Có | Có |

Ba trạng thái dữ liệu cũng phải tách rõ:

~~~text
null                   -> không có reference collection
[]                     -> có collection, không có phần tử
[null]                 -> có một phần tử là null
~~~

Chúng không tương đương. Thay null bằng list rỗng có thể đúng cho một API repository theo hợp đồng đã công bố, nhưng không được áp dụng mù quáng cho mọi DTO hoặc nghiệp vụ.

Trong migration, chữ ký 3.x kiểu `List<Account>` dưới NonNullApi không tự cho cùng mức thông tin nullness phần tử như chữ ký đó trong một null-marked context JSpecify. Cần xem implementation và dữ liệu thực tế trước khi công bố phần tử không null.

### 5.1. Wrapper không null vẫn có thể biểu diễn không có kết quả

`Optional<Account>` không null không có nghĩa luôn có Account. Nó vẫn có thể là Optional.empty.

Không thêm `@Nullable Optional<Account>` để biểu diễn việc không tìm thấy nếu hợp đồng đã dùng Optional.empty. Làm như vậy tạo thêm một trạng thái vắng mặt mà caller phải xử lý.

Tương tự, một Mono không null có thể hoàn thành rỗng. Không đổi thành publisher reference null chỉ vì query không có entity.

Với Reactor, nullable annotation trên type argument không thay đổi quy tắc tín hiệu không phát giá trị null. Cần giữ biểu diễn absence đúng với API reactive, không coi JSpecify như cơ chế cho phép null đi qua mọi wrapper.

## 6. Mảng và varargs: đổi import có thể đổi hợp đồng

### 6.1. Một chữ ký nhìn gần giống nhưng ý nghĩa khác nhau

Trong mã 3.x dùng Spring Nullable:

~~~java
import org.springframework.lang.Nullable;

public interface LegacyAliases {

    @Nullable
    String[] aliases();
}
~~~

Annotation trên return declaration diễn đạt việc reference mảng có thể null. Khi chuyển sang JSpecify, không nên chỉ thay import rồi giữ nguyên vị trí mà không đối chiếu.

Trong scope NullMarked, chữ ký sau dùng JSpecify:

~~~java
import org.jspecify.annotations.Nullable;

public interface Aliases {

    @Nullable String[] aliases();
}
~~~

lại đánh dấu **phần tử String** nullable; bản thân mảng không null theo default.

Nếu cần reference mảng nullable nhưng phần tử không null:

~~~java
String @Nullable [] aliases();
~~~

Nếu cả mảng và phần tử đều có thể null:

~~~java
@Nullable String @Nullable [] aliases();
~~~

Đây là khác biệt do TYPE_USE, không phải một thay đổi về database. Hướng dẫn migration của Spring cũng lưu ý phải chuyển vị trí annotation cho mảng/varargs để giữ đúng ý định. [Migrating Spring null-safety annotations](https://docs.spring.io/spring-framework/reference/core/null-safety.html#migrating-from-spring-null-safety-annotations).

### 6.2. Bảng đọc mảng trong NullMarked

| Chữ ký return type | Mảng có thể null? | Phần tử có thể null? |
| --- | --- | --- |
| String[] | Không | Không |
| String @Nullable [] | Có | Không |
| @Nullable String[] | Không | Có |
| @Nullable String @Nullable [] | Có | Có |

Nếu hợp đồng 3.x chưa mô tả nullness phần tử, việc chọn một trong các chữ ký mới còn là quyết định hoàn thiện hợp đồng. Không tự công bố phần tử non-null chỉ vì trước đó không có annotation phần tử.

Fixture nên phân biệt:

~~~text
null
new String[0]
new String[] { "Lan" }
new String[] { null }
~~~

Mỗi hình dạng là một trường hợp dữ liệu riêng để đối chiếu với hợp đồng đã chọn.

### 6.3. Varargs có cùng hai chiều nullness

Trong scope NullMarked:

~~~java
void acceptNullableElements(@Nullable String... aliases);

void acceptNullableArray(String @Nullable ... aliases);
~~~

Method đầu cho phép phần tử null nhưng không cho reference mảng varargs null. Method sau cho phép reference mảng null còn phần tử thông thường không null.

Khi triển khai, cần xử lý đúng những trạng thái API cho phép. Annotation cho phép null không tự tạo code xử lý null trong method body.

## 7. Generics: xét type argument và upper bound

### 7.1. Không đồng nhất List<T> với List<String>

Với một type cụ thể như String trong NullMarked, ý nghĩa default thường dễ đọc. Với T, cần xem T có thể được thay bằng kiểu nullable hay không.

Một generic class mặc định trong null-marked context:

~~~java
import org.jspecify.annotations.NullMarked;

@NullMarked
public final class RequiredBox<T> {

    private final T value;

    public RequiredBox(T value) {
        this.value = value;
    }

    public T value() {
        return value;
    }
}
~~~

Upper bound ngầm của T là Object; trong context này, bound đó không bao gồm null. Nếu thiết kế cần chấp nhận nullable type argument, phải khai báo bound phù hợp.

~~~java
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
public final class Box<T extends @Nullable Object> {

    private final T value;

    public Box(T value) {
        this.value = value;
    }

    public T value() {
        return value;
    }
}
~~~

Ở Box:

- `Box<String>` gắn với giá trị String không null.
- `Box<@Nullable String>` cho phép giá trị String hoặc null.
- T giữ nullness theo type argument; không phải mọi T đều tự trở thành nullable hoặc non-null cố định.

Đó là lý do không thêm Nullable vào mọi T để “sửa” cảnh báo generic. Cần giữ quan hệ giữa đầu vào, field và kết quả. [Các trường hợp type variable trong NullMarked API](https://jspecify.dev/docs/api/org/jspecify/annotations/NullMarked.html).

### 7.2. Generic base repository có thể làm lộ hợp đồng mới

Giả sử ứng dụng có một base repository hoặc fragment generic. Khi nâng lên API 4.x được annotate chặt hơn, compiler/checker có thể phát hiện:

- Type parameter của extension quá rộng so với bound mới.
- Implementation trả nullable trong khi interface đòi non-null.
- Mapper cho phép null nhưng collection kết quả được công bố không có phần tử null.
- Một method giữ T tùy ý nhưng tự gán null vào T không đúng thiết kế.

Cách sửa phụ thuộc ý nghĩa của extension. Có thể cần giới hạn bound hoặc thể hiện nullable type argument đúng chỗ; không dùng raw type và ép kiểu chỉ để làm hết diagnostic.

JSpecify có semantics cụ thể cho type variables và các phép chiếu nullness. Nếu thư viện có generic API phức tạp, cần đối chiếu specification thay vì áp quy tắc từ một ví dụ String. [JSpecify nullness specification](https://jspecify.dev/docs/spec/).

## 8. Override phải giữ hợp đồng của interface

Annotation trên method cha không nên được coi là sẽ tự xuất hiện trên mọi declaration override theo cùng một cách đọc metadata.

Ví dụ API JSpecify:

~~~java
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
public interface NameFormatter {
    String normalize(@Nullable String raw);
}
~~~

Implementation giữ cùng hợp đồng:

~~~java
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
public final class DefaultNameFormatter implements NameFormatter {

    @Override
    public String normalize(@Nullable String raw) {
        return raw == null ? "" : raw.trim();
    }
}
~~~

Nếu implementation bỏ Nullable trên parameter raw trong scope NullMarked, declaration đó sẽ không còn diễn đạt việc chấp nhận null như API cha.

Về nguyên tắc thay thế:

- Không thu hẹp tập đối số mà implementation phải chấp nhận so với hợp đồng cha.
- Không nới kết quả thành có thể null nếu caller của API cha được hứa non-null.
- Nếu chỉ muốn override implementation và giữ nguyên API nullness, lặp lại khai báo nullable cần thiết.
- Một thay đổi hợp đồng có chủ đích phải được đánh giá như thay đổi API, không chỉ là sửa style.

Với repository fragment, custom base repository hoặc converter, hãy kiểm tra cả interface lẫn implementation. Chỉ nhìn declaration của repository công khai có thể bỏ sót một implementation đang trả null.

## 9. Kotlin: cùng Java API có thể được nhìn rõ hơn

### 9.1. Platform type không phải hợp đồng nullable rõ ràng

Kotlin có thể nhìn một Java reference chưa có thông tin nullness như platform type, thường được IDE biểu diễn bằng ký hiệu T!.

Khi thông tin nullness được hiểu, API Java được chuyển thành kiểu Kotlin non-null hoặc nullable tương ứng. Việc một đoạn Kotlin từng compile không chứng minh Java API trước đó luôn an toàn với null.

Ví dụ Java trong scope NullMarked:

~~~java
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
public interface DisplayNameLookup {

    String requiredName();

    @Nullable String optionalName();
}
~~~

Caller Kotlin có thể xử lý:

~~~kotlin
fun describe(lookup: DisplayNameLookup): String {
    val required: String = lookup.requiredName()
    val optional: String? = lookup.optionalName()

    return required + " / " + (optional ?: "(chưa có)")
}
~~~

Nếu caller gọi `lookup.optionalName().length` không kiểm tra, diagnostic có thể xuất hiện ở compile time thay vì chờ NullPointerException runtime. Đây là một hợp đồng đã được nhìn rõ hơn, không nhất thiết là code Java vừa phát sinh thêm null.

### 9.2. JSR-305 và JSpecify có cơ chế diagnostic khác nhau

Trong dự án 3.x, cấu hình Kotlin thường có lựa chọn xử lý JSR-305, chẳng hạn:

~~~text
-Xjsr305=strict
~~~

Khi API chuyển sang JSpecify, không mặc định lựa chọn đó điều khiển cả JSpecify.

Kotlin có lựa chọn riêng:

~~~text
-Xjspecify-annotations=strict
~~~

Các mức strict, warn và ignore cần được hiểu theo compiler thực tế. Tài liệu Kotlin hiện hành mô tả strict là mặc định cho JSpecify; không áp kết luận về mặc định của compiler hiện hành cho một toolchain cũ chưa được đối chiếu. [Kotlin Java interop và JSpecify](https://kotlinlang.org/docs/java-interop.html#jspecify-support).

Đổi toàn bộ sang ignore có thể làm migration compile nhanh hơn nhưng cũng che các hợp đồng cần xử lý. Nếu dùng mức nhẹ hơn tạm thời, cần biết phần nào chưa được kiểm tra và giữ kế hoạch hoàn thiện tương ứng.

### 9.3. Override generic trong Kotlin cũng cần xét bound

Khi implement một Java generic API, Kotlin cần giữ ràng buộc non-null/nullable mà type parameter của API công bố.

Đừng đổi mọi T thành T? hoặc thêm `!!` ở mọi chỗ chỉ để làm hết lỗi. Cần xác định:

- Java declaration có default scope nào.
- Type argument có cho phép null không.
- Bound ở interface và implementation có tương thích không.
- Kết quả nullable có cần đổi hợp đồng hay xử lý absence.

Một `!!` có thể chỉ dời lỗi từ compile time sang runtime mà không giải quyết nguồn dữ liệu null.

## 10. Kiểm tra runtime của repository khác static nullness analysis

### 10.1. JSpecify không tự instrument mọi method

JSpecify định nghĩa annotation và semantics. Muốn Java build từ chối các vi phạm, cần một checker/tooling được cấu hình phù hợp. IDE diagnostic và lỗi build cũng là hai mức thực thi khác nhau.

Plain javac không tự biến tất cả khai báo non-null thành câu lệnh kiểm tra null ở đầu method. Một method tự viết vẫn phải thực hiện đúng hợp đồng mà nó công bố.

Ở phía Spring Data, repository infrastructure có thể đọc metadata và thêm kiểm tra phù hợp cho lời gọi. Đây là hành vi của framework, không phải tác dụng tự thân của annotation JSpecify trên bất kỳ object nào.

### 10.2. Validator không phải deep validator của toàn object graph

Trong implementation 4.0.0, NullnessMethodInvocationValidator kiểm tra đối số lời gọi và kết quả trả về theo nullness được xác định. Cơ chế đó không phải một phép duyệt đệ quy mọi field, phần tử list hoặc payload tương lai của publisher. [NullnessMethodInvocationValidator 4.0.0](https://github.com/spring-projects/spring-data-commons/blob/4.0.0/src/main/java/org/springframework/data/util/NullnessMethodInvocationValidator.java).

Vì vậy:

| Quan sát | Chưa đủ để kết luận |
| --- | --- |
| Repository trả List không null | Mọi phần tử và field bên trong đều hợp lệ |
| Repository trả Optional không null | Optional luôn có giá trị |
| Method trả Mono không null | Query đã chạy hoặc publisher sẽ phát một entity |
| Domain object không null | Các property bắt buộc trong store đều đúng |
| Static checker không báo lỗi | Không có boundary chưa annotate hoặc dữ liệu cũ sai hợp đồng |

Muốn kiểm tra payload, mapping và dữ liệu nguồn, cần test ở đúng tầng.

### 10.3. Scope của JSpecify không tự bằng điều kiện kích hoạt proxy validator

JSpecify định nghĩa NullMarked ở nhiều scope. Điều kiện một phiên bản Spring Data dùng để gắn validator vào repository proxy là một chi tiết tích hợp cần kiểm chứng riêng.

Ví dụ triển khai package-info ở package repository bám theo hướng dẫn và là một cách khai báo rõ ràng cho cả công cụ lẫn hạ tầng. Nếu chỉ annotate một class/method ở vị trí khác, không tự suy rằng mọi đường runtime validation tương ứng đã được bật giống hệt.

RepositoryFactorySupport 4.0.0 chọn việc thêm validator dựa trên khả năng hỗ trợ của hạ tầng nullness. Test cần đi qua repository proxy nếu muốn chứng minh cơ chế đó hoạt động. [RepositoryFactorySupport 4.0.0](https://github.com/spring-projects/spring-data-commons/blob/4.0.0/src/main/java/org/springframework/data/repository/core/support/RepositoryFactorySupport.java).

### 10.4. Các bản 3.x không phải một khối implementation bất biến

Dòng 3.5 có thay đổi tổ chức các class validator so với các dòng trước. Khi viết extension chạm vào API hạ tầng hoặc kỳ vọng chính xác một exception, cần xét bản thực tế.

Không dùng suy luận “có class tên NullnessMethodInvocationValidator nên đã có toàn bộ semantics JSpecify của 4.x”. Mã validator 3.5.0 và 4.0.0 dùng cơ chế nhận diện không hoàn toàn giống nhau. [Validator 3.5.0](https://github.com/spring-projects/spring-data-commons/blob/3.5.0/src/main/java/org/springframework/data/util/NullnessMethodInvocationValidator.java).

Việc dùng JSpecify cho API ứng dụng, khả năng đọc annotation của compiler và khả năng framework thực thi runtime là ba điều cần được đối chiếu riêng khi migration theo từng bước.

## 11. NullUnmarked hỗ trợ chuyển dần, không có nghĩa “mọi thứ nullable”

Nếu chưa thể đối chiếu đầy đủ một vùng legacy, JSpecify cung cấp NullUnmarked để quay lại trạng thái unspecified nullness cho các type usage không annotate trong scope đó.

~~~java
import org.jspecify.annotations.NullUnmarked;

@NullUnmarked
public interface LegacyNameSource {
    String findRaw(String key);
}
~~~

Chữ ký trên chưa hứa rằng kết quả luôn non-null, cũng chưa công bố rõ một hợp đồng nullable như `@Nullable String`. Đây là vùng thiếu thông tin nullness, không phải tập hợp mọi declaration đều được xem như đã annotate Nullable.

NullMarked và NullUnmarked được áp dụng theo scope bao gần nhất. Chúng phục vụ migration từng phần, nhưng cần theo dõi vùng chưa hoàn thiện thay vì dùng NullUnmarked khắp nơi để tránh diagnostic. [NullUnmarked API](https://jspecify.dev/docs/api/org/jspecify/annotations/NullUnmarked.html).

### 11.1. Đặt một boundary rõ ràng trước API mới

Ví dụ adapter của ứng dụng chủ động định nghĩa lại kết quả:

~~~java
import java.util.Objects;

import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
public final class NameReader {

    private final LegacyNameSource source;

    public NameReader(LegacyNameSource source) {
        this.source = Objects.requireNonNull(source);
    }

    public @Nullable String findName(String key) {
        String raw = source.findRaw(key);

        if (raw == null || raw.isBlank()) {
            return null;
        }

        return raw;
    }
}
~~~

API mới nói rõ:

- key là một đầu vào non-null theo hợp đồng.
- Kết quả có thể null.
- Chuỗi blank được đổi thành absence theo một quyết định của adapter.

Đó là logic ứng dụng, không phải hành vi tự sinh của NullMarked. Quyết định blank thành null cũng cần đúng yêu cầu nghiệp vụ; không áp nó cho mọi dữ liệu chỉ để tiện migration.

### 11.2. Không trộn annotation chỉ theo tên ngắn

Trong giai đoạn chuyển dần, các package có thể đang dùng hai hệ annotation khác nhau. Cần biết từng import thuộc hệ nào.

Hai import cùng tên Nullable trong một compilation unit có thể gây mơ hồ. Ngay cả khi code compile được, một import cũ còn sót lại cũng có thể khiến vị trí annotation được hiểu khác ý định mới.

Không thêm cả Spring Nullable và JSpecify Nullable lên cùng một declaration để “chắc chắn mọi công cụ đều hiểu”. Hãy chọn hợp đồng có chủ đích và kiểm tra toolchain thực tế của package đó.

## 12. Hợp đồng dữ liệu cần được đối chiếu riêng

### 12.1. Java nullable, Kotlin nullable và schema là ba góc nhìn

Giả sử dữ liệu cũ có displayName null. Một model Java/Kotlin mới công bố displayName non-null có thể làm lộ vấn đề khi materialize, kể cả khi caller không bao giờ truyền null vào repository.

Cần hỏi:

1. Null đó hợp lệ trong nghiệp vụ hay dữ liệu không hợp lệ?
2. Schema hiện tại có cho phép null không?
3. Query có select đúng field/alias không?
4. Converter hoặc constructor nào đang tạo object?
5. Hợp đồng mới cần nullable, migration dữ liệu hay từ chối dữ liệu?

Thêm JSpecify Nullable không sửa schema. Đặt cột NOT NULL cũng không tự cập nhật chữ ký API mà caller đang đọc.

Nếu dùng annotation mapping để sinh DDL trong một môi trường, vẫn phải xác nhận schema thực tế ở môi trường dùng migration riêng. Nullness của Java API không thay bằng chứng dữ liệu đã được migrate.

### 12.2. ID, version và auditing có vòng đời

Trong Spring Data, một số metadata có thể chưa có giá trị ở một giai đoạn của entity:

| Property | Câu hỏi cần đối chiếu |
| --- | --- |
| ID do store cấp | Trước save có null không, sau save lấy giá trị từ instance nào? |
| Version | Trạng thái entity mới được module nhận diện như thế nào? |
| Created/modified date | Callback/auditing cấp giá trị ở thời điểm nào? |
| Auditor | Có trường hợp không xác định được actor không? |
| Field legacy mới thêm | Dữ liệu cũ thiếu field có được đọc hợp lệ không? |

Đừng đổi Long nullable thành long với default 0 chỉ để bỏ nullable warning. Điều đó có thể làm thay đổi trạng thái persistence hoặc ý nghĩa nghiệp vụ.

Với model bất biến, kết quả save có thể là instance cần dùng để đọc ID/version đã cấp. Một field chưa đổi trên object đầu vào không tự là bằng chứng nullability mới sai.

Hợp đồng cần phản ánh các trạng thái mà ứng dụng thực sự cho phép. Có thể tách kiểu dữ liệu đầu vào và kiểu snapshot sau lưu nếu đó là thiết kế rõ ràng hơn việc một type cố diễn đạt mọi giai đoạn.

### 12.3. Projection và DTO cũng phải phản ánh nguồn dữ liệu

Một projection đọc field nullable không tự trở thành an toàn chỉ vì repository method có kết quả outer non-null.

Nếu một query không select đủ column, thêm Nullable vào DTO có thể che lỗi query thay vì biểu đạt dữ liệu hợp lệ. Cần phân biệt:

~~~text
Field được chọn và giá trị thật sự null
    khác
Field không được query cung cấp
    khác
Converter hoặc alias mapping không đúng
~~~

Mỗi trường hợp có hướng sửa khác nhau.

## 13. Dependency và công cụ phải đọc cùng hợp đồng

JSpecify được phát hành dưới artifact `org.jspecify:jspecify`; tài liệu dùng phiên bản annotation 1.0.0 làm ví dụ. Khi dự án có dependency management, cần đối chiếu với tổ hợp đã được quản lý thay vì tự nâng riêng một thành phần framework.

Hướng dẫn JSpecify khuyến nghị không giấu annotation khỏi consumer và giữ annotation khả dụng ở runtime. Với thư viện công bố API, classpath của consumer quan trọng không kém classpath biên dịch nội bộ. [Using JSpecify annotations](https://jspecify.dev/docs/using/).

Cần xác định:

| Thành phần | Điều cần biết |
| --- | --- |
| Java compiler/checker | Có thực hiện nullness analysis không, phạm vi nào? |
| IDE | Có cùng cách đọc JSpecify với build không? |
| Kotlin compiler | Phiên bản và mức diagnostic cho JSR-305/JSpecify |
| Spring Data/Framework | Runtime có đọc metadata và kích hoạt validator phù hợp không? |
| Library artifact | Annotation/default scope có được giữ và nhìn thấy ở consumer không? |
| Native/AOT artifact | Các đường kiểm tra và mapping cần thiết có được kiểm chứng không? |

Một build Java sạch trong khi IDE còn cảnh báo có thể chỉ là build chưa bật checker. Một consumer Kotlin lỗi sau khi nâng thư viện có thể đang đọc một hợp đồng chính xác hơn trước đó.

Nếu mã tự đọc annotation bằng reflection, hãy nhớ annotation type-use có thể cần được đọc từ AnnotatedType thay vì chỉ từ declaration annotation. Không viết một scanner chỉ tìm annotation tên Nullable trên method rồi cho rằng nó đã hỗ trợ đầy đủ JSpecify generics và arrays.

## 14. Quy trình migration có thể kiểm chứng

### Bước 1: Chốt hai tổ hợp phiên bản cần so sánh

Ghi nhận Spring Data, Framework, Boot nếu có, JDK, Kotlin và nullness checker thực tế.

Đối với một ứng dụng hoặc thư viện có nhiều dòng hỗ trợ, phân biệt:

- Mã nguồn nào cần compile với tổ hợp 3.x.
- Mã nguồn/artifact nào dành cho tổ hợp 4.x.
- Consumer Java/Kotlin nào cần được kiểm chứng.
- Backend và các đường mapping nào thuộc phạm vi thử nghiệm.

Không suy dependency từ tên thư mục hoặc một tài liệu của phiên bản khác.

### Bước 2: Lập hợp đồng trước khi thay annotation

Với từng API quan trọng, xác định:

~~~text
Parameter: required hay nullable?
Return outer: required, nullable hay wrapper?
Element/type argument: có thể null không?
Array/container: reference có thể null không?
Absence: empty, null hay exception?
Data boundary: giá trị null có thể đến từ đâu?
~~~

Đây là thông tin để đánh giá thay đổi, không cần tạo thêm một loại metadata runtime trong ứng dụng.

### Bước 3: Chọn scope NullMarked có chủ đích

Bắt đầu ở package hoặc API có thể đối chiếu rõ. Kiểm tra subpackage riêng, generated code, implementation và các vùng legacy.

Nếu dùng NullUnmarked tạm thời, giới hạn scope và chỉ rõ phần chưa có hợp đồng. Đừng đổi toàn bộ codebase sang default chặt hơn rồi thêm suppress diện rộng để qua build.

### Bước 4: Chuyển declaration và type-use theo ý nghĩa

Đối chiếu riêng:

- Scalar parameter/return.
- Field.
- Collection outer và element.
- Array/varargs outer và element.
- Generic upper bound.
- Interface và method override.

Mảng là trường hợp dễ đổi semantics khi chỉ thay import. Generic là trường hợp dễ làm sai quan hệ giữa các type khi sửa theo cảm tính.

### Bước 5: Sửa implementation và caller

Thay đổi cần thiết có thể gồm:

- Xử lý nullable result tại caller.
- Dùng Optional/empty representation đúng API.
- Giữ null case trong implementation override.
- Sửa converter hoặc query không cung cấp đủ dữ liệu.
- Chuẩn hóa hoặc migrate dữ liệu khi invariant thật sự yêu cầu.
- Điều chỉnh generic bound theo hợp đồng, không dùng raw type để né kiểm tra.

Không thêm một giá trị mặc định giả chỉ để biến null thành object hợp lệ. Ví dụ, tự sinh thời điểm tạo lúc đọc không bảo toàn auditing lịch sử.

### Bước 6: Chạy các tầng kiểm chứng khác nhau

| Tầng | Điều được kiểm chứng |
| --- | --- |
| Static analysis Java | Implementation và call site tuân theo annotation |
| Compile consumer Kotlin | Nullable/non-null/generic được nhìn đúng |
| Unit test | Logic xử lý null/absence của helper/adapter |
| Repository integration | Proxy, query, wrapper và mapping theo store |
| Data migration test | Dữ liệu cũ chuyển sang hợp đồng mới đúng |
| AOT/native test khi thuộc phạm vi | Artifact được tối ưu vẫn giữ hành vi cần thiết |

Một tầng qua không thay thế tầng khác. Các bước này mô tả công việc migration khi áp dụng vào dự án; không phải báo cáo đã chạy cho các đoạn minh họa trong bài.

## 15. Ma trận kiểm thử nullability cho repository và consumer

Một bộ test hữu ích cần phản ánh hợp đồng đã chọn:

| Tình huống | Kỳ vọng cần xác định |
| --- | --- |
| Parameter non-null nhận giá trị hợp lệ | Query đi đúng đường |
| Parameter nullable nhận null | Hợp đồng chấp nhận và query có semantics đúng |
| Parameter non-null bị truyền null từ boundary Java | Runtime từ chối tại đúng tầng khi validator được áp dụng |
| Query không có kết quả, return nullable | Trả null theo hợp đồng |
| Query không có kết quả, return Optional | Trả Optional.empty |
| Query không có kết quả, return bắt buộc | Báo lỗi theo cấu hình/phiên bản được kiểm chứng |
| Collection không có phần tử | Trả collection rỗng theo API repository |
| Collection có phần tử null | Được chấp nhận hay từ chối ở tầng đã xác định |
| Mảng null và mảng có phần tử null | Không nhầm hai hợp đồng type-use |
| Override của fragment/converter | Giữ đúng parameter và return contract |
| Consumer Kotlin dùng kết quả nullable | Compiler yêu cầu xử lý phù hợp |
| Dữ liệu cũ có field null/thiếu | Mapping và chính sách migration đúng |

### 15.1. Test compile và test runtime có cách tạo input khác nhau

Một negative compile test cố ý truyền nullable vào parameter non-null sẽ không thuộc cùng tập source cần build thành công bình thường.

Tương tự, test runtime muốn đưa null từ boundary Java vào repository phải được tổ chức sao cho kiểm tra tĩnh không chặn chính fixture âm đó trước khi test chạy.

Đừng tắt checker toàn dự án chỉ để tạo một test âm. Dùng fixture kiểm thử hoặc boundary được thiết kế cho mục tiêu đó, rồi vẫn kiểm tra chính sách production đúng phạm vi.

### 15.2. Không chỉ assert loại exception chung chung

Một assertion “có RuntimeException” có thể qua vì lỗi kết nối hoặc mapping, không phải vì vi phạm nullability.

Cần xác định:

- Lời gọi nào được test thực sự đi qua proxy.
- Điều kiện đầu vào/fixture nào tạo ra null.
- Lỗi đến từ validator, converter, constructor hay store.
- Kết quả absent có được biểu diễn đúng cách không.

Nếu code bắt một exception cụ thể của Spring Data, đối chiếu phiên bản và đường thực thi thay vì suy từ một class validator dùng chung. Một subclass hoặc module có thể quyết định loại lỗi cuối cùng mà caller nhận.

## 16. AOT và native: cùng hợp đồng, thêm một môi trường cần kiểm chứng

Spring AOT phân tích application context ở build time và đưa một phần discovery/decision logic ra trước runtime. Nó không tự chứng minh mọi giá trị đầu vào và dữ liệu store sẽ tuân thủ annotation nullness. [Spring AOT overview](https://docs.spring.io/spring-framework/reference/core/aot.html).

Do đó:

- AOT processing thành công không thay cho static nullness analysis.
- Static analysis thành công không thay cho kiểm thử mapping ở native artifact.
- Annotation JSpecify không tự tạo runtime hints cho mọi đoạn reflection tự viết.
- Một thư viện hỗ trợ JVM thông thường chưa tự có bằng chứng hành vi đầy đủ trên native image.

Nếu ứng dụng thuộc phạm vi AOT/native, chạy lại các tình huống null/absence quan trọng trên artifact tương ứng: required parameter, nullable result, Optional.empty, collection rỗng, DTO có field nullable và custom converter.

Nếu chỉ native artifact lỗi, hãy xác định metadata/reflective access nào thực sự cần trước khi thay đổi hợp đồng null. Không thêm Nullable lên mọi field để che một lỗi cấu hình AOT.

## 17. Các lỗi migration thường gặp

| Biểu hiện | Nguyên nhân cần xét | Hướng xử lý |
| --- | --- | --- |
| Đổi import xong mảng có nghĩa khác | Nullable chuyển từ declaration sang type-use | Đặt annotation đúng array level |
| Package con vẫn có platform type | Default không tự lan theo tên package | Kiểm tra scope của package con |
| Override mới bị cảnh báo | Parameter/return contract không còn khớp | Giữ đúng nullness của API cha |
| List không null nhưng caller lỗi ở phần tử | Outer và element nullness bị gộp | Đối chiếu type argument và dữ liệu |
| Generic extension không compile | Bound của extension và API không tương thích | Sửa bound theo semantics |
| Kotlin cần xử lý nullable sau nâng phiên bản | Thông tin nullness được đọc rõ hơn | Sửa call site hoặc sửa contract sai |
| Java build không báo vi phạm rõ ràng | Build chưa dùng checker tương ứng | Đối chiếu tooling, không suy từ javac |
| NullUnmarked dùng như Nullable | Unspecified bị hiểu thành cho phép null rõ ràng | Hoàn thiện hợp đồng theo scope |
| Runtime vẫn nhận payload không hợp lệ | Validator chỉ kiểm tra boundary nhất định | Kiểm tra mapping và nội dung dữ liệu |
| Test qua nhưng dữ liệu cũ không đọc được | Fixture chưa có null/missing legacy | Bổ sung migration/mapping scenario |

Việc deprecate annotation cũ không có nghĩa mọi code cũ lập tức biến mất hoặc mọi metadata cũ bị framework bỏ qua. Nó xác định hướng API mới; migration vẫn phải dựa vào semantics và tổ hợp phiên bản cụ thể.

## 18. Tự kiểm tra kiến thức

1. NonNullApi khác NullMarked về phạm vi thông tin nào?
2. Vì sao đổi import Nullable chưa đủ để giữ hợp đồng của mảng?
3. List<@Nullable Account> khác @Nullable List<Account> như thế nào?
4. NullUnmarked có đồng nghĩa mọi parameter và return đều nullable rõ ràng không?
5. Vì sao một generic T phải được đọc cùng upper bound?
6. Khi override một parameter nullable, bỏ annotation dưới NullMarked có thể gây vấn đề gì?
7. JSR-305 compiler option có tự điều khiển JSpecify diagnostic của Kotlin không?
8. Một repository trả collection không null chưa chứng minh gì về từng phần tử?
9. Vì sao JSpecify không thay cho schema NOT NULL hoặc kiểm thử dữ liệu cũ?
10. Khi nào ID/version/auditing cần nullable theo vòng đời thay vì thêm default giả?
11. AOT processing thành công chưa chứng minh những gì về nullability?
12. Cần những lớp bằng chứng nào để kết luận migration 3.x sang 4.x giữ đúng hợp đồng?

Đối chiếu nullability khi chuyển phiên bản cần giữ nguyên ý nghĩa của API và dữ liệu, đồng thời tận dụng độ chính xác của JSpecify ở type-use. Scope rõ ràng, implementation đúng hợp đồng, consumer Kotlin được kiểm tra và test qua repository/store thực tế giúp tránh một migration chỉ thay annotation trên bề mặt.
