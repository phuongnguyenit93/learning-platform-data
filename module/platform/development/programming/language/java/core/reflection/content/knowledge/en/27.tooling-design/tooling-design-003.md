# Không mặc định mọi field đều là dữ liệu nghiệp vụ khi thiết kế công cụ Java Reflection

## 1. Vấn đề: nhìn thấy field không có nghĩa field thuộc mô hình nghiệp vụ

`type.getDeclaredFields()` chỉ trả **khai báo vật lý**: trong `Order`, các field `orderId`, `totalCents`, `internalCache`, `traceContext`, `LOG` có thể cùng được phát hiện, nhưng không cùng thuộc một schema nghiệp vụ. Exporter cần `orderId` và `totalCents`; công cụ chẩn đoán có thể cần `traceContext`; cả hai đều phải xét quyền dữ liệu trước khi đọc giá trị.

Vì vậy phải tách **khám phá metadata**, **chọn field theo hợp đồng nghiệp vụ** và **truy cập giá trị thật**. `private`, `static`, `transient`, `synthetic` giúp phân loại cấu trúc, nhưng không tự trả lời một trường có được công bố cho người dùng hay không. Bài này tập trung vào ranh giới schema/allowlist và bảo vệ thông tin khi một công cụ dùng `Field`.

## 2. Các loại field và ý nghĩa đối với công cụ

| Dấu hiệu quan sát được | Có mặc nhiên là dữ liệu nghiệp vụ? | Cách quyết định |
| --- | --- | --- |
| `private String orderId` | **Không thể quyết định từ `private`** | Có thể là dữ liệu nghiệp vụ; dùng hợp đồng/annotation hoặc schema đã định. |
| `static final String VERSION` | Thường **không** là trạng thái của từng object | Thông thường loại khỏi projection của instance; nhưng có thể thuộc metadata chẩn đoán. |
| `static` mutable field | Thường không | Đây là trạng thái cấp class, không phải field riêng của từng instance; đọc có thể khởi tạo class. |
| `transient` | **Không tự động** loại khỏi mọi mục đích | `transient` ảnh hưởng cơ chế Java serialization mặc định, không định nghĩa hợp đồng nghiệp vụ, JSON hay persistence. |
| `final` | **Không tự động** loại | Nhiều giá trị nghiệp vụ bất biến dùng `final`, bao gồm field nền của record. |
| `synthetic` (`Field.isSynthetic()`) | Thường loại khỏi projection do ứng dụng kiểm soát | Có thể là hiện vật do compiler sinh, không nên dựa vào tên sinh ra cụ thể. |
| `enum` constant (`Field.isEnumConstant()`) | Không tự coi như field dữ liệu của mỗi đối tượng enum | Tùy công cụ muốn liệt kê hằng enum hay xuất state. |
| Field chứa cache, lazy state, lock, metric, logger, dependency | Không mặc định | Xem hợp đồng domain, role của công cụ và khả năng lộ nội bộ. |
| Field mang annotation riêng như `@BusinessData` | Có thể chọn theo **chính sách đã định** | Annotation có ý nghĩa khi công cụ định nghĩa, đọc và thực thi chính sách đó. |
| Field kế thừa từ superclass | Có thể | `getDeclaredFields()` trên subclass không tự bao gồm nó; phải duyệt hierarchy có chủ ý. |
| Field có dữ liệu nhạy cảm | Có thể **vẫn là** dữ liệu nghiệp vụ | Quyết định redaction/quyền truy cập trước khi hiển thị; không đánh đồng “nghiệp vụ” với “được phép tiết lộ”. |

**Hai lưu ý quan trọng:**

- `transient` là tín hiệu về **Java Object Serialization**, không phải bộ lọc phổ quát cho Jackson, JPA, CSV, JSON hay audit; các công nghệ đó có quy tắc và annotation riêng.
- Không nên dùng `private`, `final`, tên bắt đầu bằng dấu gạch dưới, hay tên có chứa `cache` làm tiêu chí duy nhất. Những heuristic này dễ bỏ sót dữ liệu cần thiết hoặc lộ thông tin không nên xuất.

## 3. Reflection cho ta metadata gì và không cho ta điều gì?

### 3.1. Chọn API quét đúng phạm vi

- `Class.getDeclaredFields()`: các field khai báo **trực tiếp** trên class/interface; gồm private và static, không gom field kế thừa.
- `Class.getFields()`: các field **public** có thể truy cập theo quy tắc API, gồm public field kế thừa. Dùng nó không phải cách chắc chắn để chọn business data.
- `Field.getName()`, `getType()`, `getGenericType()`, `getModifiers()`, `isSynthetic()`, `isEnumConstant()` và `getDeclaredAnnotations()`: cung cấp metadata để phân loại.
- `Modifier.isStatic(field.getModifiers())`, `Modifier.isTransient(...)`, `Modifier.isFinal(...)`: kiểm tra modifier theo quy tắc Java.
- `Class.getSuperclass()`: duyệt superclass nếu chính sách muốn chọn field kế thừa.
- `Class.isRecord()`, `Class.getRecordComponents()`: nếu xử lý record như dữ liệu mang tính cấu trúc, record components thường là điểm xuất phát phù hợp hơn quét field tùy ý.

Java **không bảo đảm thứ tự** các field trả về bởi `getDeclaredFields()`. Nếu output dùng cho snapshot, file xuất, hash hoặc kiểm thử, phải định nghĩa thứ tự riêng (ví dụ sắp xếp theo tên kèm declaring class hoặc thứ tự schema).

### 3.2. Từ cấu trúc tới ý nghĩa nghiệp vụ cần một hợp đồng

`Field.getType() == String.class` chỉ cho biết **kiểu khai báo** của field, không cho biết chuỗi đó là mã đơn hàng, access token hay metadata tạm. Tương tự, `Field.isSynthetic() == false` chỉ nói field không được đánh dấu synthetic; nó vẫn có thể thuộc hạ tầng.

Các cách làm rõ hợp đồng:

1. **Allowlist schema**: liệt kê tên và kiểu được xuất; thay đổi có review và versioning.
2. **Annotation opt-in**: dùng `@BusinessData` hoặc annotation của chính công cụ; mặc định field không được đánh dấu sẽ bị bỏ.
3. **DTO/record projection**: chuyển domain object thành kiểu công khai riêng; thường dễ kiểm soát hơn đọc trực tiếp field.
4. **Metadata từ framework/domain**: khi xử lý entity, bean hoặc serialization, đọc metadata/hợp đồng thực tế của framework đó thay vì tự suy luận chỉ từ JVM field.

Nhiều công cụ nên dùng **kết hợp**: chọn field theo schema/annotation, xác thực access policy, kiểm tra nhạy cảm, rồi mới đọc giá trị và chuyển đổi.

## 4. Quy trình chọn field có thể bảo vệ và kiểm chứng

Đề xuất một pipeline khi viết field inspector hoặc exporter:

1. **Chốt mục đích đầu ra**: xuất dữ liệu nghiệp vụ, debug, audit, migration hay validation? Mỗi mục đích có chính sách riêng.
2. **Xác định phạm vi kiểu**: kiểu gốc, superclass nào cần xét, interface/record component/property hay field trực tiếp? Tránh duyệt vô hạn vào thư viện/JDK.
3. **Lọc metadata trước**: `isSynthetic`, `static`, modifier, annotation, kiểu, declaring class, các điều kiện loại trừ rõ ràng. Không gọi `Field.get` trong pha lọc metadata.
4. **Áp dụng allowlist và quyền dữ liệu**: mặc định không xuất field chưa được chấp thuận; dữ liệu nhạy cảm có thể bị che hoặc bị bỏ tùy người nhận.
5. **Kiểm tra truy cập một cách tường minh**: dùng API public, accessor được phép hoặc `trySetAccessible()` nếu thật sự cần và được module cho phép; thất bại thì xử lý/ghi nhận có kiểm soát.
6. **Đọc/biến đổi giá trị và bảo vệ output**: phân biệt `null`, chuẩn hóa kiểu/đơn vị, che secrets, giới hạn độ sâu của object graph, chống vòng lặp và định dạng đầu ra ổn định.
7. **Kiểm thử thay đổi schema**: thêm field mới không nên làm nó tự xuất hiện trong API/audit ngoài ý muốn. Dùng test cụ thể đối với allowlist, redaction và field kế thừa.

**Fail closed** cho dữ liệu có quyền riêng tư cao: nếu một field mới chưa được phê duyệt, đừng xuất nó. Nhưng không nhất thiết ném lỗi cho mọi field kỹ thuật bị bỏ; cách xử lý phải phản ánh hợp đồng và mức nghiêm ngặt của pipeline.

## 5. Ví dụ Java 17+: kiểm tra metadata và xuất các field được chọn

Chương trình minh họa một **chính sách của ứng dụng mẫu**, không phải quy tắc có sẵn của Reflection:

- Chọn field có `@BusinessData` (`RUNTIME`, `FIELD`).
- Bỏ `static` và `synthetic`; ở **demo này** còn bỏ `transient`.
- Bỏ field không có `@BusinessData`.
- Field có `@Sensitive` vẫn là thông tin nghiệp vụ nhưng **không đọc hoặc in giá trị**.
- Duyệt superclass có chủ ý và sắp xếp từng nhóm field theo tên để đầu ra ổn định.
- Chỉ sau các bước lọc mới gọi `trySetAccessible()` rồi `Field.get(target)`. Ví dụ đặt các class trong cùng file, chạy từ classpath nên thao tác này được phép.

Lưu thành file **`BusinessFieldSelectionDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;

public class BusinessFieldSelectionDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    @interface BusinessData {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    @interface Sensitive {}

    static class OrderBase {
        @BusinessData private final String tenantId = "tenant-a";
        private final String traceSource = "batch";
    }

    static class Order extends OrderBase {
        private static final String CACHE_VERSION = "v1";
        @BusinessData private final String orderId = "A-17";
        @BusinessData private final int totalCents = 2500;
        @BusinessData @Sensitive private final String customerEmail = "a@example.com";
        private transient String draftNote = "review";
        private String internalCache = "ready";
    }

    static void inspect(Object target) throws IllegalAccessException {
        for (Class<?> type = target.getClass();
             type != null && type != Object.class;
             type = type.getSuperclass()) {
            Field[] fields = type.getDeclaredFields();
            Arrays.sort(fields, Comparator.comparing(Field::getName));
            for (Field field : fields) {
                String label = type.getSimpleName() + "." + field.getName();
                int modifiers = field.getModifiers();
                if (field.isSynthetic()) {
                    System.out.println(label + " -> skip: synthetic");
                } else if (Modifier.isStatic(modifiers)) {
                    System.out.println(label + " -> skip: static");
                } else if (Modifier.isTransient(modifiers)) {
                    System.out.println(label + " -> skip: transient (demo policy)");
                } else if (!field.isAnnotationPresent(BusinessData.class)) {
                    System.out.println(label + " -> skip: not annotated");
                } else if (field.isAnnotationPresent(Sensitive.class)) {
                    System.out.println(label + " -> REDACTED");
                } else if (!field.trySetAccessible()) {
                    System.out.println(label + " -> inaccessible");
                } else {
                    System.out.println(label + " -> " + field.get(target));
                }
            }
        }
    }

    public static void main(String[] args) throws IllegalAccessException {
        inspect(new Order());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 BusinessFieldSelectionDemo.java
java BusinessFieldSelectionDemo
```

**Đầu ra đã kiểm chứng**:

```text
Order.CACHE_VERSION -> skip: static
Order.customerEmail -> REDACTED
Order.draftNote -> skip: transient (demo policy)
Order.internalCache -> skip: not annotated
Order.orderId -> A-17
Order.totalCents -> 2500
OrderBase.tenantId -> tenant-a
OrderBase.traceSource -> skip: not annotated
```

**Phân tích đầu ra:**

1. `CACHE_VERSION` là field của class, không phải state riêng của `Order`; trình xuất instance bỏ nó.
2. `customerEmail` mang cả `@BusinessData` và `@Sensitive`. Thông tin đó **có ý nghĩa nghiệp vụ nhưng không được tiết lộ**. Demo không gọi `Field.get` trên field này.
3. `draftNote` bị bỏ bởi **chính sách demo**, không phải vì mọi công cụ Java đều phải bỏ `transient`.
4. `internalCache` có thể hữu ích cho debug, nhưng không có `@BusinessData` nên không đi vào projection nghiệp vụ.
5. `orderId` và `totalCents` được chọn, truy cập và in ra. `final` không ngăn việc đọc, cũng không làm mất ý nghĩa nghiệp vụ.
6. `tenantId` là private field thuộc `OrderBase`; duyệt superclass giúp tìm nó. `traceSource` được nhìn thấy ở metadata nhưng không được xuất vì thiếu annotation.
7. Chương trình hiển thị quyết định cho từng field để phục vụ học tập; trong hệ thống thực tế, **đừng log tên hoặc metadata nhạy cảm nếu chính sách cấm**. Thông thường exporter chỉ trả các trường được phê duyệt, còn việc từ chối được ghi trong kênh kiểm toán phù hợp.

Annotation `@BusinessData` trong mã không tự thực thi hành vi; **phương thức `inspect` mới là bộ xử lý**. Nếu bỏ `@Retention(RetentionPolicy.RUNTIME)`, annotation không nhất thiết tồn tại trong metadata runtime để `isAnnotationPresent` kiểm tra; nếu bỏ `@Target(ElementType.FIELD)` thì annotation có thể không đúng mục tiêu thiết kế.

## 6. Field và property không phải lúc nào cũng tương ứng 1–1

### 6.1. JavaBeans và getter

Một *property* có thể được công khai qua `getTotal()`, `isActive()` hoặc accessor khác dù không có field cùng tên. Ngược lại, một field cache có thể không có accessor nào trong public API. Framework dựa trên getter/property và framework dựa trên field access có thể xây ra hai schema khác nhau.

Không nên tùy tiện gọi tất cả phương thức bắt đầu bằng `get` để “kiểm tra dữ liệu”: getter có thể truy vấn database, tải lazy association, tính toán tốn kém, thay đổi cache hoặc ném exception. Nếu cần introspection property, phải đọc đúng hợp đồng JavaBeans/framework và kiểm soát lúc thực thi accessor.

### 6.2. Record từ Java 16+

Với:

```java
record OrderView(String orderId, int totalCents) {}
```

Đây là **khai báo kiểu minh họa**, không phải ứng dụng độc lập. `OrderView.class.isRecord()` là `true` và `getRecordComponents()` cho metadata của `orderId`, `totalCents` theo **thứ tự khai báo trong record header**. Nếu chính sách muốn tạo projection từ record components, nên bắt đầu ở API `RecordComponent` và hợp đồng record, thay vì mặc định mọi field bên trong record là trường dữ liệu.

Chú ý annotation của *record component*, field nền và accessor có các quy tắc về `@Target` riêng. **Không giả định** một annotation đặt trên record component luôn xuất hiện đúng như mong muốn trên `Field`; phải kiểm tra thiết kế annotation và metadata mà công cụ thực sự đọc.

### 6.3. ORM, serializer và framework

Các trường hợp như JPA entity, JSON model, dependency injection hoặc object do framework sinh thường có hợp đồng riêng:

- Một entity có thể dùng **field access** hoặc **property access**; không suy đoán mapping chỉ từ danh sách field.
- Annotation `@Transient` của JPA, từ khóa Java `transient` và cách Jackson quyết định serialize là các cơ chế khác nhau.
- Proxy/lazy-loading object có thể chứa state hạ tầng; Reflection trên **runtime class** của proxy có thể trả field khác so với domain class được dự định.
- Các thư viện serializer có thể xử lý annotation, getter, record component, accessor visibility và naming strategy; quét `getDeclaredFields()` không tái tạo đầy đủ hành vi đó.

Nếu mục đích là xuất JSON hoặc dữ liệu persistence, ưu tiên **chính schema/mapper của công nghệ được dùng** thay vì dựng lại một hệ thống mapping khác từ field thô.

## 7. Kế thừa, field hiding và định danh ổn định

`getDeclaredFields()` không nhận field của superclass; ví dụ đã duyệt chuỗi `getSuperclass()`. Nhưng việc duyệt này đưa ra thêm câu hỏi:

- **Field hiding:** subclass và superclass có thể cùng khai báo một field tên `code`, đây là **hai field khác nhau** với `getDeclaringClass()` khác nhau; sơ đồ chỉ dựa vào tên `"code"` có thể ghi đè một field. Hãy dùng định danh gồm declaring class + field name, hoặc đặt quy tắc ưu tiên rõ ràng trong schema.
- **Interface constants:** interface có field `public static final`. Một inspector state của instance không nên tự coi chúng là thuộc tính nghiệp vụ.
- **Phạm vi superclass:** đối tượng ứng dụng có thể kế thừa lớp framework với nhiều field kỹ thuật. Không quét không giới hạn vào mọi superclass nếu hợp đồng chỉ thuộc một miền kiểu được quản lý.
- **Thứ tự:** sắp xếp tùy mục đích; nếu schema có thứ tự đã công bố, hãy dùng thứ tự của schema thay vì alphabetical để tránh breaking change.

`Field.getDeclaringClass()` chỉ nơi field được khai báo; `target.getClass()` xác định runtime type. Cả hai hữu ích khi kết quả quét cần audit rõ ràng.

## 8. Quyền truy cập, an toàn dữ liệu và tác dụng phụ

### 8.1. Không dựa vào `setAccessible(true)` vô điều kiện

`Field.trySetAccessible()` trả `false` khi không thể bật quyền truy cập theo mô hình module; `setAccessible(true)` có thể ném `InaccessibleObjectException`. Trong named module, package chưa `opens` phù hợp có thể chặn Reflection vào thành viên non-public. Đừng tự động đề xuất `--add-opens` chỉ để xuất dữ liệu nếu đã có API công khai/DTO.

Trong ví dụ, cả các lớp nằm cùng một file classpath, nên `trySetAccessible()` thành công. Một thư viện reusable cần xử lý trường hợp không thành công (bỏ field có kiểm soát, báo thiếu quyền hoặc chuyển sang accessor được phép), đồng thời không nuốt lỗi khiến báo cáo sai âm thầm.

### 8.2. Đọc giá trị phải có lý do

- `Field.get(target)` đọc **giá trị runtime**, khác hẳn `getType()` hoặc `getModifiers()` chỉ đọc metadata.
- Đọc `static` field có thể kích hoạt **class initialization**. Ví dụ chọn bỏ static trước khi đọc giúp tránh rủi ro không cần thiết này.
- Thông tin có thể đổi đồng thời do thread khác; một lần quét nhiều field không tự là snapshot nguyên tử.
- Giá trị là object tham chiếu, collection hoặc graph có vòng lặp. Nếu tiếp tục truy sâu phải có giới hạn độ sâu, visited identity set, timeout/budget và quy tắc loại nội dung nhạy cảm.
- Đừng gọi `toString()` bừa bãi trên object chưa tin cậy: implementation có thể thực hiện I/O, tạo log, kích hoạt lazy loading hoặc in secrets. Trong demo, các giá trị được chọn chỉ là `String` và primitive `int`.

Một chính sách tốt lọc **trước khi đọc**, tránh giữ plaintext nhạy cảm trong bộ đệm/log trung gian rồi mới “redact” ở cuối.

### 8.3. Quyền đọc và quyền xuất là hai cấp khác nhau

Dù Reflection được phép đọc field, điều đó **không** khẳng định người nhận được phép xem nó. Phải xác định vai trò/ngữ cảnh truy cập, tập dữ liệu cho phép, redaction, audit, lưu trữ và thời hạn giữ dữ liệu ở layer ứng dụng.

Ví dụ `email` hoặc `tenantId` có thể là dữ liệu nghiệp vụ hợp lệ, nhưng endpoint xuất công khai cần ẩn/bỏ, còn một công cụ quản trị có thể được cấp quyền khác. Đây là quyết định domain/security, không phải kết quả tự động của `Field.isSynthetic()` hay modifier.

## 9. Những anti-pattern cần tránh

| Mẫu sai | Vấn đề | Thay thế |
| --- | --- | --- |
| `for (Field f : c.getDeclaredFields()) out.put(f.getName(), f.get(obj));` | Có thể lộ field riêng tư/kỹ thuật, có access error, tên field trùng và output không ổn định. | Allowlist/annotation/schema, lọc metadata, truy cập đúng quyền, redaction. |
| Bỏ mọi field `private` | Mất dữ liệu nghiệp vụ đang được đóng gói. | Chọn theo contract; lấy giá trị bằng public accessor khi phù hợp. |
| Chỉ bỏ `static` rồi coi phần còn lại là domain data | Bao gồm cache, transient, token, synthetic và state framework. | Áp dụng chính sách nhiều bước, mặc định opt-in. |
| Coi `transient` là “không thuộc nghiệp vụ” trong mọi trường hợp | Trộn hợp đồng Java serialization với domain mapping. | Chính sách riêng cho từng đầu ra/framework. |
| Coi `!isSynthetic()` là bằng chứng an toàn | Compiler flag không mô tả sensitivity hay ownership. | Dùng allowlist và metadata nghiệp vụ. |
| Tự động gọi mọi getter và duyệt object graph vô hạn | Có thể gây side effect, N+1 queries, vòng lặp, lộ secrets. | DTO hoặc API schema riêng, budget và cycle detection. |
| Sắp xếp mặc định dựa vào thứ tự `getDeclaredFields()` | Reflection không bảo đảm thứ tự. | Sort hoặc schema order. |
| Bật `setAccessible(true)` cho mọi field | Va chạm module boundary, mở quá mức, không cần thiết. | Chọn field trước, dùng accessor/DTO hoặc truy cập có kiểm soát. |

## 10. Bài tập áp dụng

1. Thêm `@BusinessData private final String currency = "VND";` vào `Order`, dự đoán nơi nó xuất hiện trong output và kiểm tra thứ tự do `Arrays.sort`.
2. Gắn `@BusinessData` vào `internalCache`. Tại sao annotation opt-in lúc này khiến nó được xuất, dù tên cho thấy có thể là hạ tầng? Thiết kế thêm một kiểm tra schema/owner review để ngăn sai sót người khai báo.
3. Gỡ `@Sensitive` khỏi `customerEmail` và quan sát chính sách demo thay đổi như thế nào. Vì sao tác động này cần review security?
4. Thêm một field tên `orderId` vào `OrderBase`. Nếu exporter dùng map chỉ có key là tên field, điều gì xảy ra? Hãy sử dụng `getDeclaringClass()` để tránh trùng.
5. Thử tạo `record OrderView(String orderId, int totalCents) {}` và in các `RecordComponent`. So sánh cách chọn schema record với duyệt `getDeclaredFields()`.
6. Thiết kế hai projection khác nhau: **audit nội bộ** và **JSON công khai**. Nêu rõ allowlist, quyền, mức redaction và chính sách xử lý field chưa biết.

**Checklist trước khi đưa một field vào đầu ra:** Ai sở hữu ý nghĩa của field? Nó thuộc schema/contract phiên bản nào? Có annotation/allowlist phê duyệt không? Là field instance hay state hạ tầng? Có nhạy cảm không? Có thể đọc hợp lệ không? Việc đọc có side effect hoặc snapshot không nhất quán không? Đối tượng sẽ được biểu diễn bằng giá trị nguyên thủy, DTO hay traversal an toàn? Có kiểm thử khi lớp thêm field mới không?

## 11. Tài liệu tham khảo

- [Java SE 17 — Class.getDeclaredFields(), getFields(), getRecordComponents()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — java.lang.reflect.Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 17 — java.lang.reflect.Modifier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html)
- [Java SE 17 — AccessibleObject.trySetAccessible()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html#trySetAccessible())
- [Java SE 17 — java.lang.reflect.RecordComponent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html)