# Định nghĩa chính sách field, property hoặc accessor cần dùng trong công cụ Java Reflection

## 1. Vì sao phải có chính sách thay vì quét mọi member?

Khi xây một công cụ dùng reflection (serializer, object inspector, mapper, validator, form generator, exporter...), cùng một giá trị có thể xuất hiện dưới nhiều hình thức:

- **Field**: vùng lưu trữ như `private String name` hoặc `public int count`, được mô tả bởi `java.lang.reflect.Field`.
- **JavaBeans property**: thuộc tính logic xác định qua cặp phương thức theo quy ước, ví dụ `getName()` / `setName(String)`, hoặc `isActive()` cho boolean; có thể **không có field cùng tên**. Metadata thường được đọc qua `java.beans.Introspector` và `PropertyDescriptor`.
- **Record component**: thành phần khai báo trong header của record, ví dụ `record User(String name) {}`, có accessor `name()` và `RecordComponent` riêng.
- **Accessor tùy biến**: phương thức có ngữ nghĩa lấy dữ liệu như `displayName()` hoặc `fetchBalance()`; không phải mọi method không tham số đều nên trở thành property.

Nếu công cụ vừa quét field, vừa quét getter, nó có thể xuất `name` hai lần; nếu ép gọi tất cả getter, có thể làm phát sinh truy vấn cơ sở dữ liệu, lỗi nghiệp vụ hoặc làm lộ thông tin. Nếu tùy tiện dùng `setAccessible(true)`, công cụ có thể vi phạm ranh giới module hoặc đọc dữ liệu không được phép.

**Chính sách truy cập (access policy)** là quy tắc xác định rõ *nguồn metadata*, *đối tượng nào được chọn*, *cách đặt tên*, *quyền đọc/ghi*, *ưu tiên khi trùng*, *thứ tự đầu ra*, *xử lý lỗi* và *ranh giới bảo mật*. Chính sách cần được quyết định trước khi quét/đọc object; không để hành vi vô tình phụ thuộc thứ tự trả về của `getDeclaredFields()` hay `getDeclaredMethods()`.

### Một số tình huống

| Bối cảnh | Chính sách có thể phù hợp | Điểm cần kiểm soát |
| --- | --- | --- |
| Inspector đơn giản trên DTO có public fields | Public instance fields | Không suy đoán private fields cũng được phép đọc |
| Framework dùng hợp đồng JavaBeans | Getter/setter hợp lệ từ `Introspector` | Loại getter lỗi, getter có tác dụng phụ; kiểm tra quyền |
| Export dữ liệu record | Record components theo header | Dùng `getRecordComponents()` và accessor `name()`, không giả định tên `getName()` |
| API serializer dữ liệu nhạy cảm | Explicit allowlist + annotation/config | Chỉ xuất trường được chấp thuận; bảo vệ secret |
| Framework có domain object hỗn hợp | Chính sách rõ ràng theo loại hoặc theo annotation | Tránh tự động gộp/ghi đè field và property trùng tên |

## 2. Phân biệt đúng field, property và accessor

### Field: lưu trữ trực tiếp

Với:

```java
class Account {
    private String name;
    public String alias;
}
```

`Account.class.getDeclaredFields()` tìm field **khai báo ngay trên lớp** (bao gồm private), còn `Account.class.getFields()` tìm public fields khả dụng, gồm các public fields được kế thừa. Hai API này có phạm vi khác nhau; `getDeclaredFields()` không tự lấy field kế thừa.

Phát hiện field bằng metadata không có nghĩa chương trình có quyền đọc giá trị. `Field.get(target)` cần receiver hợp lệ và quyền truy cập thích hợp. Với static field, đối số target được bỏ qua; với instance field, target phải là instance tương thích. Java reflection cũng có `Field.getInt`, `getBoolean`... cho primitive.

**Field không tương đương property**: một field có thể là dữ liệu nội bộ; một property có thể tính toán giá trị hoặc ủy quyền vào hệ thống khác. Không tự động serialize mọi private field chỉ vì công cụ đủ quyền kỹ thuật để làm vậy.

### JavaBeans property: hợp đồng phương thức

`Introspector.getBeanInfo(type, Object.class).getPropertyDescriptors()` trả metadata property theo JavaBeans convention, bỏ qua phần đến từ `Object` theo mức stop class. Một `PropertyDescriptor` có thể cung cấp:

- `getName()`: tên logic, chẳng hạn `active`.
- `getReadMethod()`: getter nếu có.
- `getWriteMethod()`: setter nếu có.
- `getPropertyType()`: kiểu property khi xác định được.

Ví dụ `boolean isActive()` theo quy ước JavaBeans thường tạo property `active`; `getBalance()` có thể là property chỉ đọc nếu không có setter. Một setter-only property có `getReadMethod() == null` và **không thể đọc** chỉ dựa trên descriptor đó.

`Introspector.decapitalize` có quy tắc tên riêng, ví dụ `getURL()` thường ánh xạ property `URL` chứ không phải `uRL`. Đừng tự chuyển tên bằng cách hạ chữ cái đầu trong mọi trường hợp. Các JavaBeans descriptor đến từ inheritance và `BeanInfo` tùy biến có thể khác suy luận đơn giản từ tên method.

### Record component: hợp đồng header record

Ví dụ:

```java
public record Receipt(String code, int total) {}
```

`Receipt.class.isRecord()` là `true`. `Receipt.class.getRecordComponents()` trả các `RecordComponent` theo thứ tự khai báo: `code`, `total`. Accessor là `code()`, `total()`, **không phải** `getCode()` hay `getTotal()`. `getRecordComponents()` trả `null` với class không phải record, vì vậy phải kiểm tra `isRecord()` trước.

Record components không tự đồng nhất với JavaBeans properties trong mọi công cụ: JavaBeans introspection truyền thống dựa vào `getX()/isX()`, trong khi record accessor được đặt theo tên thành phần. Nếu công cụ phải hỗ trợ record, hãy quy định riêng nhánh record.

### Accessor tùy biến: chỉ nhận khi có hợp đồng

Một `public String displayName()` không có tham số **chưa chắc** là property. Nếu công cụ chọn các accessor không theo JavaBeans, cần có điều kiện minh bạch như annotation `@Expose`, metadata do người dùng khai báo hoặc interface chuẩn của ứng dụng. Không quét tất cả zero-argument methods rồi gọi thử: có thể gặp `close()`, `reset()`, `delete()` hoặc thao tác tốn kém, mặc dù một số có kiểu trả về phù hợp.

## 3. Những quyết định chính sách cần chốt

Trước khi viết bộ quét, ghi rõ câu trả lời cho các câu hỏi sau:

| Quyết định | Các lựa chọn thường gặp | Khuyến nghị triển khai |
| --- | --- | --- |
| Nguồn thành viên | `PUBLIC_FIELD`, `BEAN_PROPERTY`, `RECORD_COMPONENT`, `ANNOTATED_ACCESSOR` hoặc phối hợp | Chọn một mặc định xác định; có override có chủ đích |
| Thành viên được chọn | Public-only, allowlist, annotation, visibility do module cho phép | Public + allowlist mặc định cho dữ liệu xuất ra ngoài |
| Instance/static | Chỉ instance hay gồm cả static | Thông thường loại static vì không thuộc trạng thái một object |
| Synthetic/bridge | Có tính thành viên do compiler tạo không | Loại synthetic field/method và bridge method nếu quét method thô |
| Mutable/read-only | Đọc, ghi hay cả hai | Phân tách `readable` và `writable`; không suy từ tồn tại field |
| Kế thừa | Lấy member inherited hay chỉ declared | Ghi rõ từng API; xử lý override/hiding |
| Tên public | Field name, bean property name, record component name hoặc annotation alias | Chuẩn hóa tên đầu ra và kiểm tra trùng |
| Thứ tự | Theo header record, theo tên, theo annotation `order` | Quy định rõ, không dựa vào thứ tự reflection trả về |
| Null & lỗi getter | Giữ null, bỏ qua, ghi lỗi theo đường dẫn | Không im lặng đổi null thành chuỗi `"null"` |
| Trùng tên | Ưu tiên nào? lỗi? | Mặc định báo ambiguity; chỉ ưu tiên khi policy công bố |
| Quyền truy cập | Public, `privateLookupIn`, `setAccessible` có điều kiện | Tôn trọng module boundary, hạn chế deep reflection |
| Hiệu năng | Introspect mỗi lần hoặc cache metadata | Cache descriptor theo `Class<?>`; không cache giá trị object tùy tiện |

**Policy phải dựa vào mục tiêu đầu ra:** serializer phục vụ API public thường có ranh giới khác debugger nội bộ; policy đọc (export) cũng khác policy ghi (binding/deserialization). Tránh một cờ `includeAll=true` gom tất cả trường hợp với nhiều hệ quả khó dự đoán.

## 4. Mô hình policy và quy trình duyệt đề xuất

Một bản thiết kế có thể gồm ba lớp:

1. **Discovery**: từ `Class<?>` lấy danh sách field, property, record component hoặc accessor đã đăng ký theo policy.
2. **Selection & normalization**: áp dụng allowlist/denylist/annotation, loại static/synthetic, xác định tên logic, visibility, nullability, readable/writable, xử lý trùng và sắp xếp ổn định.
3. **Execution**: chỉ khi được yêu cầu, gọi `Field.get` hoặc getter/record accessor; ghi kết quả, phân loại exception và không để lỗi một property làm hỏng toàn bộ dữ liệu nếu hợp đồng cho phép partial result.

Ví dụ descriptor trung gian (fragment, chưa phải chương trình đầy đủ):

```java
enum SourceKind { FIELD, BEAN, RECORD, EXPLICIT_ACCESSOR }

record MemberDescriptor(
        String externalName,
        Class<?> valueType,
        SourceKind sourceKind,
        boolean readable,
        boolean writable
) {}
```

Trong hệ thống thật, descriptor nên có strategy thực thi có kiểm soát, ví dụ hàm đọc/ghi hoặc tham chiếu `Field`/`Method`/`MethodHandle`, và metadata về annotation/ownership. **Đừng tự chọn cách đọc bằng chuỗi tên** sau khi đã nhận descriptor: tên có thể bị alias, override hoặc trùng.

Quy tắc đề xuất cho `AUTO`: nếu target là record thì dùng record components; nếu là bean do ứng dụng định nghĩa thì dùng JavaBeans; nếu muốn public fields thì chọn rõ `PUBLIC_FIELD`. Đây chỉ là **một chính sách do công cụ tự định nghĩa**, không phải hành vi tự động của JVM hay reflection API. Muốn phối hợp nhiều nguồn, thiết kế precedence riêng, ví dụ explicit annotation → record → JavaBeans → public field, và báo trùng khi hai nguồn không cùng ngữ nghĩa.

Luồng quyết định:

```text
target + policy
    |
    +-- record && policy=AUTO ? RECORD_COMPONENT
    |
    +-- policy=AUTO ? BEAN_PROPERTY
    |
    +-- policy explicit ? nguồn tương ứng
    |
    v
metadata -> filter -> normalize names -> collision check
    -> stable order -> access check -> execute accessor -> result
```

## 5. Ví dụ Java 17+ hoàn chỉnh: cùng object, ba cách đọc

Chương trình sau cố ý hỗ trợ **ba chế độ tách biệt**:

- `PUBLIC_FIELD`: đọc public, non-static, non-synthetic fields.
- `BEAN_PROPERTY`: đọc getter được phát hiện bằng JavaBeans `Introspector`; bỏ property chỉ ghi, chỉ đọc `getReadMethod() != null`.
- `RECORD_COMPONENT`: đọc chính các component của record.
- `AUTO` là chính sách do chương trình chọn: record dùng record component; object khác dùng JavaBeans. Nó không cố hợp nhất hai nguồn.

Lưu thành **`AccessPolicyDemo.java`**:

```java
import java.beans.IntrospectionException;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.RecordComponent;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class AccessPolicyDemo {
    enum Strategy { PUBLIC_FIELD, BEAN_PROPERTY, RECORD_COMPONENT, AUTO }

    public static final class Account {
        public String alias = "alpha";
        private int credits = 7;

        public int getCredits() { return credits; }
        public void setCredits(int credits) { this.credits = credits; }
        public boolean isActive() { return true; }
    }

    public record Receipt(String code, int total) {}

    record Entry(String name, Object value) {}

    static List<Entry> read(Object target, Strategy requested)
            throws ReflectiveOperationException, IntrospectionException {
        Objects.requireNonNull(target, "target");
        Class<?> type = target.getClass();

        Strategy mode = requested == Strategy.AUTO
                ? (type.isRecord()
                        ? Strategy.RECORD_COMPONENT
                        : Strategy.BEAN_PROPERTY)
                : requested;

        List<Entry> entries = new ArrayList<>();
        switch (mode) {
            case PUBLIC_FIELD -> {
                for (Field field : type.getFields()) {
                    if (field.isSynthetic()
                            || Modifier.isStatic(field.getModifiers())) {
                        continue;
                    }
                    entries.add(new Entry(field.getName(), field.get(target)));
                }
            }
            case BEAN_PROPERTY -> {
                for (PropertyDescriptor p :
                        Introspector.getBeanInfo(type, Object.class)
                                .getPropertyDescriptors()) {
                    Method getter = p.getReadMethod();
                    if (getter == null
                            || Modifier.isStatic(getter.getModifiers())) {
                        continue;
                    }
                    entries.add(new Entry(p.getName(), getter.invoke(target)));
                }
            }
            case RECORD_COMPONENT -> {
                if (!type.isRecord()) {
                    throw new IllegalArgumentException(
                            "RECORD_COMPONENT requires a record");
                }
                for (RecordComponent component : type.getRecordComponents()) {
                    entries.add(new Entry(
                            component.getName(),
                            component.getAccessor().invoke(target)));
                }
            }
            default -> throw new IllegalStateException(
                    "Unsupported mode: " + mode);
        }

        entries.sort(Comparator.comparing(Entry::name));
        return entries;
    }

    static String describe(Object target, Strategy strategy)
            throws ReflectiveOperationException, IntrospectionException {
        return read(target, strategy).stream()
                .map(entry -> entry.name() + "=" + entry.value())
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) throws Exception {
        Account account = new Account();
        Receipt receipt = new Receipt("R1", 45);

        System.out.println("FIELD(Account): "
                + describe(account, Strategy.PUBLIC_FIELD));
        System.out.println("BEAN(Account): "
                + describe(account, Strategy.BEAN_PROPERTY));
        System.out.println("AUTO(Account): "
                + describe(account, Strategy.AUTO));
        System.out.println("RECORD(Receipt): "
                + describe(receipt, Strategy.RECORD_COMPONENT));
        System.out.println("AUTO(Receipt): "
                + describe(receipt, Strategy.AUTO));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 AccessPolicyDemo.java
java AccessPolicyDemo
```

Stdout chính xác:

```text
FIELD(Account): alias=alpha
BEAN(Account): active=true, credits=7
AUTO(Account): active=true, credits=7
RECORD(Receipt): code=R1, total=45
AUTO(Receipt): code=R1, total=45
```

Giải thích kết quả:

- `Account.alias` là public field nên được chọn bởi `PUBLIC_FIELD`. `credits` là private field, không xuất hiện trong danh sách `getFields()`.
- JavaBeans nhìn thấy `getCredits()` và `isActive()`, nên đọc `credits=7` và `active=true`. Nó không suy ra một JavaBeans property từ riêng field `alias`.
- `Receipt` là record: `getRecordComponents()` nhận `code` và `total`; accessor tương ứng là `code()` và `total()`. Chính sách `AUTO` dùng nhánh record.
- Thứ tự đầu ra ổn định vì chương trình **chủ động sort theo tên**. Thứ tự xuất hiện trong phản hồi của các API reflection nói chung không nên được xem là hợp đồng sắp xếp.
- Ví dụ dùng các nested type thuộc chương trình kiểm soát, không cần `setAccessible(true)`. Đối tượng chứa bên thứ ba có thể đặt ra yêu cầu quyền/module khác.

Đây là ví dụ **read-only**, chưa xử lý alias, annotation, deep reflection, duplicate-name hay lỗi từng getter. Trong công cụ thực tế, các quy tắc bên dưới cần được cấu hình thêm trước khi đưa vào xử lý dữ liệu người dùng.

## 6. Chính sách lọc, đặt tên và giải quyết xung đột

### 6.1. Whitelist có chủ đích

Không nên mặc định xuất tất cả field/getter tìm được. Ví dụ entity có `getPasswordHash()`, `getApiToken()` hoặc `getInternalAuditTrail()`. Dù method là public, điều đó không tự làm thông tin thích hợp cho API hay file xuất.

Một chính sách chắc chắn hơn:

- Có allowlist tên property hoặc annotation riêng của công cụ (ví dụ `@Exportable`) được xem xét trong phạm vi khai báo và nơi đặt annotation hợp lệ.
- Có denylist cho dữ liệu nhạy cảm như secret, nhưng **allowlist mới là cơ chế kiểm soát chính** khi dữ liệu đi ra ranh giới tin cậy.
- Nếu một property không thuộc allowlist, bỏ qua **trước khi gọi getter**, tránh chạy code không cần thiết.
- Định nghĩa điều kiện annotation nằm trên field, getter, record component hay parameter, và việc kế thừa/override được xử lý ra sao. Không giả định annotation trên field tự chuyển sang getter hoặc ngược lại.

Ví dụ pseudocode cho chính sách đọc (không phải API có sẵn trong JDK):

```java
// Minh họa thuật toán; selected và policy do công cụ của bạn định nghĩa.
for (MemberDescriptor member : selected) {
    if (!policy.isAllowed(member.externalName())) continue;
    if (!member.readable()) continue;
    // Chỉ lúc này mới thực thi accessor và đưa vào kết quả.
}
```

### 6.2. Tên trùng và ưu tiên nguồn

Giả sử có `private String name`, `getName()` và record component `name`. Nếu quét nhiều nguồn, ba mục này có thể đại diện cùng một thuộc tính logic hoặc có ngữ nghĩa khác nhau (getter trả giá trị tính toán). Nếu gộp tùy tiện bằng `Map.put`, thứ tự duyệt quyết định giá trị nào thắng, dễ gây lỗi khó tái hiện.

Chốt một trong hai hợp đồng:

1. **Chỉ một nguồn mỗi class** theo policy, như ví dụ `AccessPolicyDemo`: tránh phần lớn xung đột.
2. **Kết hợp nhiều nguồn theo precedence rõ ràng**, ví dụ annotation khai báo cụ thể có quyền ưu tiên, rồi record component, JavaBeans property, public field. Nếu cùng cấp có hai ứng viên khác nhau hoặc alias đụng nhau, báo `AMBIGUOUS_PROPERTY` với tên, declaring class và source.

Không dựa vào `getDeclaredMethods()` hay `getDeclaredFields()` để xác định precedence. Kiểm tra field hiding giữa cha/con, getter override và inheritance để tránh chọn nhầm member cũ. Nếu cần hỗ trợ alias, kiểm tra trùng **sau khi đã áp dụng alias**, không chỉ trên Java identifier ban đầu.

### 6.3. Thứ tự cố định

Serializer hoặc công cụ sinh schema có thể cần kết quả ổn định để snapshot test, hash và diff không thay đổi ngẫu nhiên. Quy định thứ tự: alphabet theo external name; hoặc theo `order` explicit; hoặc thứ tự record components trong header khi cần tương thích schema. Ví dụ đang sort alphabet cho tất cả để nhất quán.

## 7. Read policy khác write policy

Một property đọc được chưa chắc ghi được:

| Nguồn | Đọc | Ghi | Ghi chú |
| --- | --- | --- | --- |
| Public non-final field | Thường có thể bằng `Field.get` | Có thể bằng `Field.set` nếu quyền và kiểu hợp lệ | Không suy ra atomic/thread safety |
| Private field | Tùy quyền reflection/module | Tùy quyền, có thể bị giới hạn | Không tự deep-reflect vì tiện |
| JavaBeans getter-only | Có | Không có setter theo descriptor | Getter có thể tính toán/có side effect |
| JavaBeans setter-only | Không có getter | Có setter phù hợp | Không đoán giá trị hiện tại |
| Record component | Accessor có | Không thể ghi như mutable property | Tạo record mới qua constructor khi cần thay đổi giá trị |
| Static field | Không thuộc state instance theo policy thông thường | Cần chính sách riêng | Nên loại khỏi serializer instance |

Với JavaBeans, kiểm tra `getReadMethod()` và `getWriteMethod()` riêng. Với field, xét `Modifier.isFinal` và quyền truy cập. Record có các field thành phần `private final`, nhưng quan trọng hơn, public API record thể hiện một cấu trúc giá trị không hỗ trợ sửa component sau khi tạo; mutation của object được tham chiếu bên trong vẫn có thể xảy ra (shallow immutability).

**Việc validate type** phải dựa vào hợp đồng của API dùng để gán: `Field.set` và `Method.invoke` có ràng buộc kiểu/primitive conversion riêng; không tự chuyển chuỗi `"42"` thành `int` nếu không có conversion policy đã định nghĩa. Khi binding dữ liệu người dùng, validation, coercion và access policy là các quyết định tách biệt.

## 8. Quyền truy cập và lỗi runtime

### Giới hạn của Java Platform Module System

Tìm được `getDeclaredField("secret")` không chứng tỏ có thể đọc field đó. `setAccessible(true)` không luôn hợp lệ dưới strong encapsulation; có thể ném `InaccessibleObjectException`. `trySetAccessible()` có thể trả false khi không được phép. `MethodHandles.privateLookupIn` cũng yêu cầu caller có quyền và điều kiện module phù hợp; nó không phải đường vòng qua Java access control.

Cho công cụ dùng trong sản phẩm, ưu tiên public contract/annotation rõ ràng, mở package chính xác nếu bắt buộc và được chủ sở hữu module cho phép. Không tự đặt `--add-opens ALL-UNNAMED` tràn lan chỉ để vượt quyền đọc dữ liệu.

### Xử lý lỗi getter, field và record accessor

Một getter có thể ném ngoại lệ do logic nghiệp vụ, side effect hoặc I/O. `Method.invoke` bọc ngoại lệ từ code đích trong `InvocationTargetException`; còn `Field.get` có thể ném `IllegalAccessException` hay `IllegalArgumentException` khi receiver không hợp lệ. `RecordComponent.getAccessor().invoke` cũng là gọi một `Method`, nên cần xử lý ngoại lệ tương tự. Đừng nuốt exception rồi ghi một giá trị `null` khó phân biệt.

Ví dụ thiết kế result (fragment):

```java
record ReadIssue(
        String propertyName,
        String sourceKind,
        String errorCode,
        String message
) {}
```

Có thể có các chính sách lỗi như fail-fast cho hệ thống giao dịch, hoặc collect-errors khi làm object inspector nội bộ. Nếu trả partial result, phải đánh dấu rõ mục nào lỗi và không được xem nó là giá trị `null` thực sự. Cần tránh log full value/stack trace ra API response vì getter có thể chạm tới dữ liệu cá nhân hoặc secret.

## 9. Hiệu năng, ổn định và khả năng mở rộng

Phần tốn công của một công cụ reflection thường là discovery, chuẩn hóa và quyết định quyền, nên có thể cache **metadata descriptors** theo `Class<?>` và policy version; không cache giá trị của từng instance dưới cùng key vì giá trị thay đổi theo object.

- **Cache theo class/policy**: `ClassValue<T>` là lựa chọn đáng cân nhắc khi muốn cache gắn với lifecycle của `Class`; đối với `Introspector`, JDK đã có cơ chế cache `BeanInfo` riêng. Nếu công cụ dùng classloader động hoặc hot reload, đánh giá nguy cơ giữ tham chiếu classloader.
- **Cache decision**: lưu các member đã lọc và thứ tự chuẩn hóa để tránh lặp lại thao tác trên mỗi object; invalidation khi policy/annotation mapping thay đổi.
- **MethodHandle**: có thể cân nhắc khi có lời gọi lặp lại đủ nhiều và biết chữ ký; việc chuyển từ `Method` sang handle không thay thế discovery policy. Không khẳng định `MethodHandle` luôn nhanh hơn `Method.invoke`, vì JDK, warm-up và workload ảnh hưởng kết quả.
- **Thread-safety**: cache metadata bất biến và cấu trúc concurrent phù hợp; không lẫn cache với đồng bộ giá trị mutable của bean.
- **Cycle detection**: nếu serializer duyệt object graph, phải tách chính sách chọn property khỏi cơ chế xử lý tham chiếu vòng và giới hạn độ sâu. Không phải property nào cũng được phép recursively expand.

Tạo test dựa trên các trường hợp như getter-only, setter-only, record, inherited getter, field hiding, private field, static/synthetic, annotation allowlist, duplicate alias, getter throwing, JPMS, classloader. Thứ tự ổn định làm kết quả dễ đối chiếu giữa các phiên chạy.

## 10. Checklist quyết định và lỗi thường gặp

Trước khi chốt policy của công cụ, trả lời:

1. Công cụ này phục vụ mục tiêu gì: serialization, binding, diagnostics, schema generation hay test introspection?
2. Nguồn mặc định là public field, JavaBeans property, record component hay accessor đăng ký riêng?
3. Ai được phép tham gia: mọi public member hay chỉ allowlist được duyệt?
4. Có cho private access không, và module chủ sở hữu có cho phép không?
5. Static, synthetic, bridge, transient, final, inherited được xử lý ra sao?
6. Getter-only/setter-only, alias, null, duplicate name và exception được biểu diễn thế nào?
7. Kết quả có yêu cầu thứ tự ổn định và backward compatibility của schema không?
8. Có cache metadata theo class/policy và xử lý unload/reload classloader không?

Các sai lầm cần tránh:

- **“Có field là có property”**: JavaBeans có thể không có field; getter có thể tính toán.
- **“Record accessor luôn tên `getX`”**: thực tế accessor mặc định theo component name, như `code()`.
- **“Method public nào không tham số cũng an toàn để gọi”**: getter có thể side effect, và nhiều method không phải accessor.
- **“Quét `getDeclaredFields` là đã lấy toàn bộ inheritance”**: nó chỉ lấy field khai báo trực tiếp.
- **“`setAccessible(true)` luôn mở khóa được”**: còn access checks và module boundaries.
- **“Dùng cả field lẫn getter luôn đầy đủ hơn”**: có thể sinh duplicate, dữ liệu nội bộ và giá trị khác nhau; cần precedence và policy.
- **“Có getter thì chắc chắn ghi được”**: write contract là chuyện riêng; record component về bản chất không phải mutable property.
- **“Đầu ra reflection có thứ tự cố định”**: phải định nghĩa/sort rõ nếu cần ổn định.

Tự kiểm tra:

- Một lớp có `private int age` cùng `getAge()`: `PUBLIC_FIELD` và `BEAN_PROPERTY` cùng chọn `age` không? **Không**; public-field policy không chọn private field, bean policy có thể chọn getter.
- `record Point(int x, int y)`, chỉ dùng `Introspector` mặc định liệu có bảo đảm lấy được `x`/`y`? **Không**; nên dùng `getRecordComponents()` khi chủ đích hỗ trợ record.
- Getter `getSecret()` là public, liệu nên tự động xuất secret? **Không**; API public không tự đồng nghĩa được xuất ra bên ngoài.
- Khi hai accessor cùng alias `userId`, liệu chọn phần tử duyệt sau có an toàn? **Không**; cần deterministic precedence hoặc báo collision.
- Một inspector cần hiển thị 100 bean nhiều lần: tối ưu bước nào trước? **Cache metadata/selection policy**, rồi đo hiệu năng execution nếu thực sự cần.

Tài liệu gốc: [`Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [`Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html), [`Introspector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/Introspector.html), [`PropertyDescriptor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyDescriptor.html), [`RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html) và [JavaBeans Specification](https://www.oracle.com/java/technologies/javase/javabeans-spec.html).