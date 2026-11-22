# Quy tắc nhận diện interface MXBean trong Java JMX

## 1. Vì sao “có đuôi MXBean” chưa phải toàn bộ câu chuyện?

Trong Java Management Extensions (JMX), **MXBean** là kiểu MBean chuyên dùng để xuất dữ liệu quản trị/giám sát theo những loại có thể ánh xạ thành **Open Types**, giúp công cụ JMX không cần phải biết mọi lớp Java riêng của ứng dụng. Lớp API liên quan nằm ở module `java.management`, package `javax.management`; đây là các API **hiện hành trên Java 17+**, dù chủ đề học có tên module Java 6.

Muốn xuất một interface quản trị thành MXBean, có ít nhất **ba câu hỏi khác nhau**:

1. **Interface nào được nhận diện là MXBean interface?** Quy tắc gồm `public`, hậu tố `MXBean` hoặc annotation `@MXBean` và khả năng opt-out.
2. **Object khi được đăng ký trong MBeanServer có được chọn làm MXBean không?** Quá trình nhận diện còn xét `DynamicMBean`, Standard MBean naming convention, số lượng các MXBean interfaces và quan hệ kế thừa.
3. **Interface được chọn có hợp lệ để xuất như MXBean không?** Getters, setters, operations và các kiểu dữ liệu phải phù hợp quy tắc JMX/OpenType mapping.

Nhầm ba bước này sẽ dẫn tới các hiện tượng rất khó hiểu: `JMX.isMXBeanInterface(MyMXBean.class)` báo `true` nhưng một wrapper `StandardMBean` lại có descriptor `mxbean=false`; hoặc tên đúng hậu tố `MXBean` nhưng MBean đăng ký thất bại vì trả về kiểu không ánh xạ được.

**Nguyên tắc:** Tên và annotation là **điều kiện nhận diện**, không thay cho đăng ký đúng loại, kiểm tra giao diện quản trị và quy tắc chuyển đổi kiểu dữ liệu.

## 2. Phân biệt MXBean interface, MXBean instance và ObjectName

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Java `interface` | Hợp đồng quản trị có methods/attributes | `CacheMXBean` |
| Java implementation object | Object có trạng thái và logic thực tế | `new Cache()` |
| `MBeanServer` | Nơi quản lý những MBean đã đăng ký | `MBeanServerFactory.createMBeanServer()` |
| `ObjectName` | Danh tính của một MBean instance trong server | `demo.mx:type=Cache` |
| `JMX.isMXBeanInterface(Class<?>)` | API kiểm tra interface có đủ điều kiện **nhận diện MXBean** | `JMX.isMXBeanInterface(CacheMXBean.class)` |
| `StandardMBean` | Wrapper có thể xuất object thành Standard MBean hoặc MXBean | Constructor `(object, interface, true)` |
| `JMX.newMXBeanProxy` | Typed proxy dùng MXBean mapping | `JMX.newMXBeanProxy(server, name, CacheMXBean.class)` |
| `JMX.newMBeanProxy` | Typed proxy cho Standard MBean | `JMX.newMBeanProxy(...)` |
| `MBeanInfo`/`Descriptor` | Metadata thực tế của MBean đã đăng ký | `getFieldValue(JMX.MXBEAN_FIELD)` |

Một interface không “tự khởi động” JMX server. Bạn phải có implementation object và đăng ký nó vào `MBeanServer` bằng `registerMBean` hoặc wrapper thích hợp. `ObjectName` là tên của **instance** đã đăng ký, không phải quy tắc tên Java interface. Ví dụ `demo.mx:type=Cache` không cần kết thúc bằng `MXBean`.

### 2.1. Sơ đồ toàn bộ quy trình

~~~text
Public Java interface?
    |
    +-- Ends with "MXBean" AND not @MXBean(false)?
    |          OR
    +-- Explicit @MXBean / @MXBean(true)?
    |
    v
Recognized MXBean interface candidate
    |
    +-- Direct register object:
    |       DynamicMBean? -> Dynamic path first
    |       Standard MBean naming? -> Standard path first
    |       Otherwise inspect MXBean candidates
    |
    +-- Explicit StandardMBean(..., true):
    |       Force wrapper to use MXBean semantics
    |
    v
Check management interface compliance
    |
    +-- Getter/setter and operation naming
    +-- Java type to OpenType mapping
    +-- Reconstructible parameters
    |
    v
Registered MBean + MBeanInfo Descriptor
    |
    v
JMX proxy / management client
~~~

Trong code production, cần kiểm cả classification **và** descriptor sau đăng ký, thay vì chỉ suy luận từ hậu tố tên.

## 3. Quy tắc #1 — interface phải là public

Theo Java SE 26 JavaDoc `javax.management.MXBean` và `JMX.isMXBeanInterface`, ứng viên MXBean interface phải là **public**.

Ví dụ hợp lệ:

~~~java
public interface CacheMXBean {
    int getSize();
}
~~~

Ví dụ không tự được nhận diện như MXBean interface:

~~~java
interface HiddenMXBean {
    int getSize();
}
~~~

Đây là **hai snippet minh họa**, không đặt chung trong một source file `public` nếu tên file không tương ứng. Với nested interface, khai báo `public interface` trong một public enclosing class cũng là một cách tạo type public.

Điểm thường nhầm:

- Class implementation có thể `public`, nhưng management interface package-private vẫn không được nhận diện bằng quy tắc này.
- Chỉ đổi class implementation từ package-private sang public **không sửa** interface chưa public.
- Annotation `@MXBean` không phải một lệnh cấp quyền/public; interface vẫn cần có visibility đúng.
- Runtime/module visibility và class-loading cũng ảnh hưởng việc các clients JMX truy cập mô hình quản trị; không nên xuất types private rồi mong công cụ generic tự tái tạo.

Chương trình kiểm thử sẽ đối chiếu `HiddenMXBean` (nested interface không public) và nhận `false`.

## 4. Quy tắc #2 — hậu tố tên chính xác `MXBean`

Nếu một **public interface** chưa có `@MXBean` annotation, JMX nhận diện nó theo convention khi tên kết thúc bằng chuỗi **`MXBean`**. Ví dụ:

~~~java
public interface CacheMXBean {
    int getSize();
    void clear();
}
~~~

Tên `CacheMXBean` hợp lệ vì có hậu tố chính xác. Đây là convention của interface, **không yêu cầu implementation class cũng tên `Cache`** trong mọi kiểu đăng ký; điều đó phụ thuộc direct registration hay wrapper.

Những tên **không tự kích hoạt** convention:

~~~java
public interface CacheControl {
    int getSize();
}

public interface CacheMxBean {
    int getSize();
}

public interface CacheMXBeanView {
    int getSize();
}
~~~

Các đoạn trên chỉ là **mẫu declarations**. `CacheMxBean` viết khác chữ hoa/chữ thường; `CacheMXBeanView` có `MXBean` nhưng **không ở cuối tên**. Convention dùng exact suffix, không phải chứa substring hoặc suy đoán về ý định tác giả.

Tên interface hoàn toàn bình thường như `CacheControl` vẫn có thể được nhận diện bằng `@MXBean` (quy tắc #3).

### 4.1. Tên không phải tiêu chí duy nhất về độ hợp lệ

Ngay cả `CacheMXBean` là public và đúng tên, nếu getter nhận hoặc trả kiểu không mappable sang OpenType, việc dựng/đăng ký như một MXBean có thể thất bại. Ví dụ một getter trả kiểu `Object` tùy ý không thể tự được chuyển thành bất kỳ OpenType nào.

Do đó có thể viết unit test cho **naming/annotation** và integration test khác cho **registration/type mapping**, không đánh đồng.

## 5. Quy tắc #3 — `@MXBean` và `@MXBean(true)`

Annotation hiện hành:

~~~java
import javax.management.MXBean;

@MXBean
public interface ServiceView {
    String getMode();
}
~~~

Theo `@MXBean` JavaDoc, annotation không ghi giá trị có mặc định **`value() == true`**. Vì vậy:

~~~java
@MXBean(true)
public interface ServiceView {
    String getMode();
}
~~~

Cũng mang ý nghĩa nhận diện là MXBean interface. Trong cùng một source file, chỉ nên dùng **một trong hai declaration**, không khai báo cùng tên hai lần.

Khi annotation là true, interface **không cần** hậu tố `MXBean`. Ví dụ `ServiceView` và `ActiveView` trong chương trình chạy đều được `JMX.isMXBeanInterface(...)` nhận là MXBean candidates dù không có suffix.

### 5.1. Annotation trên interface chứ không phải thay thế interface

~~~java
@MXBean
public interface ServiceView {
    String getMode();
}

public final class Service implements ServiceView {
    @Override
    public String getMode() {
        return "safe";
    }
}
~~~

Mô hình đúng là định nghĩa **contract interface**, rồi implementation class implements nó. Dù annotation `@MXBean` có `@Target(TYPE)`, quy tắc nhận diện ở đây xét **Java interface**; gắn annotation vào một concrete class mà không có management interface phù hợp **không biến nó thành MXBean interface**.

### 5.2. Annotation là metadata runtime

`@MXBean` có `RetentionPolicy.RUNTIME`, nên JMX/provider có thể xét annotation bằng reflection. Nó không được hiểu như một Spring annotation tự khởi tạo bean; JMX registration vẫn là công việc riêng.

## 6. Quy tắc #4 — `@MXBean(false)` có quyền ưu tiên so với tên

Đây là trường hợp rất hay bị bỏ sót:

~~~java
@MXBean(false)
public interface LegacyMXBean {
    String getValue();
}
~~~

Dù `LegacyMXBean` là public và **kết thúc bằng `MXBean`**, annotation **`false`** làm nó **không** được tự nhận diện là MXBean interface. JMX không chỉ kiểm suffix rồi trả true.

So sánh:

| Interface | `JMX.isMXBeanInterface` |
| --- | --- |
| `public interface CacheMXBean`, không annotation | `true` |
| `@MXBean public interface ServiceView` | `true` |
| `@MXBean(true) public interface ActiveView` | `true` |
| `@MXBean(false) public interface LegacyMXBean` | `false` |
| `public interface OrdinaryView`, không suffix/annotation | `false` |
| `interface HiddenMXBean`, không public | `false` |
| Concrete class `NotAnInterface` | `false` |

**Khi dùng `@MXBean(false)`**: thường là do bạn đã có một interface vô tình kết thúc bằng `MXBean` nhưng không muốn JMX tự xuất nó như MXBean. Không nên dùng nó để “tắt giám sát an toàn” thay cho access control; nó chỉ ảnh hưởng **tự động nhận diện**, không ngăn một thành phần có quyền tạo wrapper `StandardMBean(...,true)` rõ ràng.

### 6.1. Một ngoại lệ quan trọng: explicit wrapper flag

Hai ý cần tách biệt:

- `JMX.isMXBeanInterface(LegacyMXBean.class) == false` — do annotation false.
- `new StandardMBean(new Legacy(), LegacyMXBean.class, true)` — người lập trình **chủ động yêu cầu** wrapper dùng MXBean semantics.

Constructor explicit `isMXBean=true` không đơn thuần “hỏi interface đó có tên đúng không”; nó chọn cách diễn giải management interface trong wrapper. Test thứ hai chứng minh có thể ép wrapper sử dụng MXBean semantics với interface opt-out **khi các kiểu phương thức vẫn hợp lệ**.

**Không nên lạm dụng:** Dùng `@MXBean(false)` cùng với ép `true` làm code khó hiểu; nếu thật sự muốn xuất MXBean, sửa contract/annotation rõ ràng hơn. Điều cần nắm là **annotation naming classification khác explicit wrapper configuration**.

## 7. Quy tắc #5 — annotation không tự truyền sang interface con

Java annotation `@MXBean` không mang quy tắc tự động “mọi interface con cũng được đánh dấu”. Ví dụ:

~~~java
@MXBean
public interface ServiceView {
    String getMode();
}

public interface ChildView extends ServiceView {
}
~~~

`JMX.isMXBeanInterface(ServiceView.class)` là `true`; còn `ChildView` **không có annotation riêng và không có suffix MXBean**, nên `JMX.isMXBeanInterface(ChildView.class)` là `false` trong kiểm thử Java 17/JDK24.

Nếu muốn interface con **cũng** được tự nhận diện, hãy:

~~~java
@MXBean
public interface ChildView extends ServiceView {
    int getLevel();
}
~~~

Hoặc đặt tên interface con kết thúc bằng `MXBean` nếu phù hợp naming convention.

**Cẩn thận phân biệt với quá trình đăng ký một object thực thi nhiều interfaces:** JMX có quy tắc chọn interface *most specific* nếu một MXBean interface là subinterface của tất cả MXBean candidate interfaces khác. Điều đó **không** làm annotation tự được kế thừa thành `@MXBean` trên mọi interface con.

## 8. API `JMX.isMXBeanInterface(Class<?>)`: kiểm tra đúng thứ cần kiểm

Java SE 26 cung cấp:

~~~java
boolean recognized =
        JMX.isMXBeanInterface(CacheMXBean.class);
~~~

Đây là API tĩnh hiện hành trong `javax.management.JMX`. Nó hữu ích để test convention và annotation trước khi viết code đăng ký.

Những lưu ý:

- Đối số là **`Class<?>`**; không phải instance object hay `ObjectName`.
- Không truyền `null`; JavaDoc chỉ rõ `JMX.isMXBeanInterface(null)` ném `NullPointerException`.
- Với concrete class, method trả `false` vì class không phải interface.
- Với package-private interface, trả `false` dù tên có suffix.
- Với public interface được annotation `@MXBean(false)`, trả `false` dù tên đúng suffix.
- Với public interface annotation true, không cần suffix.

### 8.1. Nhận diện không phải là “đăng ký đã thành công”

Giả sử code:

~~~java
if (JMX.isMXBeanInterface(CacheMXBean.class)) {
    // Chỉ xác nhận quy tắc interface, chưa có MXBean nào được đăng ký.
}
~~~

Chưa có `MBeanServer.registerMBean`, cũng chưa kiểm getter/operation mapping. Một hệ thống quản trị cần ít nhất:

1. Nhận diện interface dự kiến.
2. Kiểm object implements interface và management methods hợp lệ.
3. Đăng ký vào MBeanServer theo semantics MXBean.
4. Kiểm descriptor/result và khả năng đọc/ghi từ MBeanServer hoặc proxy.
5. Quản lý quyền truy cập, vòng đời, unregister.

Một số lỗi về OpenType mapping chỉ xuất hiện ở bước tạo wrapper/proxy hoặc đăng ký; method nhận diện không chứng minh toàn bộ hoạt động sẽ thành công.

## 9. Quá trình **direct registration** chọn loại MBean như thế nào?

Khi gọi:

~~~java
server.registerMBean(implementation, objectName);
~~~

Với `implementation` là object **không được wrap bởi StandardMBean**, JMX theo quy tắc được mô tả trong `@MXBean` JavaDoc:

1. Nếu class implements `DynamicMBean`: xử lý theo Dynamic MBean path. `StandardMBean` chính nó implements `DynamicMBean`, nên wrapper đi theo nhánh này.
2. Nếu class phù hợp **Standard MBean naming convention**: nó được xem là Standard MBean trước.
3. Nếu chưa khớp hai nhánh trên: xét những interface MXBean candidates mà class implements (kể cả qua kế thừa).
4. Nếu chỉ có **một** MXBean interface candidate, chọn nó.
5. Nếu có **nhiều**, vẫn có thể chọn một interface là **subinterface của tất cả** các candidates còn lại.
6. Nếu không có candidate phù hợp, hoặc không có candidate duy nhất có thể chọn, việc đăng ký bị từ chối (thường `NotCompliantMBeanException`).

**Ưu tiên Standard MBean trước MXBean là chi tiết quan trọng.** Một implementation class tên `Dual` implements `DualMBean` và `DualMXBean` có thể được nhận diện thành **Standard MBean** khi direct register, dù `DualMXBean` bản thân cũng là MXBean interface hợp lệ.

### 9.1. Sơ đồ ưu tiên

~~~text
registerMBean(object, objectName)
             |
             v
object implements DynamicMBean?
       | yes          | no
       v              v
  Dynamic path   Matches ClassNameMBean pattern?
                        | yes          | no
                        v              v
                  Standard MBean   Collect MXBean candidates
                                        |
                                  count / specificity
                                   /      |       \
                                  1     subtype    ambiguous
                                  |        |           |
                                  v        v           v
                                 MXBean  MXBean      Reject
~~~

Đừng tự viết reflection scanner sử dụng `clazz.getSimpleName().endsWith("MXBean")` để thay thuật toán JMX. MBeanServer có thứ tự ưu tiên và xử lý nhiều interfaces mà shortcut đó bỏ qua.

### 9.2. Trường hợp một interface con được ưu tiên

~~~java
public interface BaseMXBean {
    int getCount();
}

public interface ExtendedMXBean extends BaseMXBean {
    String getName();
}

public final class Extended implements ExtendedMXBean {
    public int getCount() { return 7; }
    public String getName() { return "child"; }
}
~~~

Khi direct-register `new Extended()`, MXBean candidates bao gồm `BaseMXBean` và `ExtendedMXBean`; interface con `ExtendedMXBean` cụ thể hơn và được chọn. Ví dụ thứ hai xác minh đăng ký thành công, descriptor `mxbean=true` và đọc thuộc tính `Name`.

### 9.3. Trường hợp nhiều MXBean unrelated bị từ chối

~~~java
public interface LeftMXBean {
    int getLeft();
}

public interface RightMXBean {
    int getRight();
}

public final class Ambiguous
        implements LeftMXBean, RightMXBean {
    public int getLeft() { return 1; }
    public int getRight() { return 2; }
}
~~~

Không có interface nào là subinterface của interface còn lại, nên **direct registration không chọn được một management interface duy nhất** và ném `NotCompliantMBeanException`. Có thể tránh mơ hồ bằng cách chọn một interface quản trị thống nhất hoặc explicit wrapper `StandardMBean(impl, chosenInterface, true)` khi phù hợp; đừng tùy tiện export mọi method.

## 10. `StandardMBean` wrapper: hai và ba tham số khác nhau

Một nhầm lẫn thực tế đã được kiểm thử trên JDK24:

~~~java
StandardMBean standard =
        new StandardMBean(new Cache(), CacheMXBean.class);
~~~

Mặc dù interface tên `CacheMXBean` được `JMX.isMXBeanInterface(...)` nhận, constructor **hai tham số** trên tạo **Standard MBean** wrapper theo JavaDoc. Descriptor `mxbean` là false trong kiểm thử.

Để explicit tạo **MXBean** wrapper:

~~~java
StandardMBean mxbean =
        new StandardMBean(new Cache(), CacheMXBean.class, true);
~~~

`true` là tham số `isMXBean`. Khi đó JMX làm **MXBean mapping**; chẳng hạn `List<String>` được xuất qua OpenData như `String[]`.

| Cách tạo/đăng ký | Hành vi cần nhớ |
| --- | --- |
| `server.registerMBean(new Cache(), name)` | Direct classification: kiểm Dynamic/Standard naming rồi tìm MXBean candidates |
| `new StandardMBean(new Cache(), CacheMXBean.class)` | **Standard MBean wrapper** (hai tham số) |
| `new StandardMBean(new Cache(), CacheMXBean.class, false)` | **Standard MBean wrapper** |
| `new StandardMBean(new Cache(), CacheMXBean.class, true)` | **MXBean wrapper** |
| `new StandardMBean(new Legacy(), LegacyMXBean.class)` với `@MXBean(false)` | Standard MBean wrapper phù hợp opt-out |
| `new StandardMBean(new Legacy(), LegacyMXBean.class, true)` | Ép explicit MXBean semantics nếu contract/type mapping hợp lệ |

Các snippets yêu cầu `Cache`/`Legacy` classes và interface tương ứng từ chương trình ở mục 14. Không copy từng dòng vào source chưa có definitions rồi kỳ vọng biên dịch độc lập.

### 10.1. Khi nào dùng StandardMBean wrapper?

- Tên implementation class không theo direct naming convention, nhưng interface quản trị rõ ràng.
- Muốn chọn đúng **một** interface khi object implements nhiều interfaces.
- Muốn tường minh Standard vs MXBean semantics bằng `isMXBean`.
- Muốn custom MBeanInfo/descriptions qua subclass `StandardMBean` theo API phù hợp.
- Muốn tránh phụ thuộc vào auto-selection khi hệ thống có nhiều hợp đồng quản trị.

Tuy wrapper là `DynamicMBean`, `StandardMBean` ở đây **không phải một API cũ bị thay thế**; nó vẫn là công cụ được Java SE 26 hỗ trợ.

### 10.2. Constructor không tự làm điều mà application phải làm

Wrapper chỉ quyết định cách export management interface; nó không tạo TCP listener, không bật JMX remote và không tự cấp authentication. Tất cả điều đó là phần riêng của triển khai quản trị/monitoring.

## 11. MXBean compliance: Java type phải chuyển sang OpenType

Khác biệt lớn nhất giữa MXBean và Standard MBean là **Open Types**. MXBean được thiết kế để công cụ tổng quát có thể đọc dữ liệu mà không tải classes riêng của ứng dụng. JMX định nghĩa cách ánh xạ types, ví dụ:

| Java type trong interface | OpenData tương ứng | Ghi chú |
| --- | --- | --- |
| `int`, `long`, `boolean` | `SimpleType.INTEGER/LONG/BOOLEAN` và boxed Java values | Dữ liệu primitive |
| `String` | `SimpleType.STRING` | Kiểu trực tiếp |
| `ObjectName` | `SimpleType.OBJECTNAME` | Tham chiếu MBean |
| `String[]` | `ArrayType` | Mảng |
| `List<String>` | `String[]` dưới `ArrayType(SimpleType.STRING)` | Đã kiểm bằng `MBeanServer.getAttribute` |
| `Set<String>` | Open array representation | Quản lý semantics/reconstruction |
| `enum` | `String` | Tên enum |
| `Map<K,V>` có K,V hợp lệ | `TabularData` | Key và value phải mappable |
| Một Java record/bean đủ điều kiện | `CompositeData` | Phụ thuộc mapping/reconstruction rules |
| Một MXBean interface reference | `ObjectName` | Subject to MXBean reference rules |
| `Object` tùy ý | **Không tự có mapping hợp lệ** | Không nên export làm arbitrary Object |

**Type mapping** cũng xét **reconstructibility**: khi client gửi parameter qua proxy, MXBean phải tái tạo được giá trị Java từ OpenData; phía client proxy cần reconstruction cho return types khi đọc. Không tự suy luận rằng mọi `List<MyCustomType>`/`Map<Object,Object>` đều hoạt động.

### 11.1. Ví dụ `List<String>`: bằng chứng OpenType

Interface:

~~~java
public interface CacheMXBean {
    List<String> getTags();
}
~~~

Implementation trả `List.of("alpha", "beta")`. Với **MXBean đã đăng ký**, gọi:

~~~java
Object raw = server.getAttribute(name, "Tags");
boolean isOpen = raw instanceof String[];
~~~

Test nhận `isOpen == true`. Với typed MXBean proxy:

~~~java
CacheMXBean proxy =
        JMX.newMXBeanProxy(server, name, CacheMXBean.class);

List<String> tags = proxy.getTags();
~~~

Proxy ánh xạ dữ liệu từ `String[]` về `List<String>` theo contract. **Standard MBean** wrapper hai tham số không áp MXBean OpenType conversion theo cùng cách; điều này có thể làm các công cụ remote/generic gặp vấn đề với model-specific Java objects.

### 11.2. Hậu tố tên đúng nhưng type mapping vẫn sai

~~~java
public interface InvalidTypeMXBean {
    Object getAnything();
}
~~~

Hậu tố và visibility đúng; nhưng một `Object` tùy ý không có MXBean OpenType mapping tổng quát. Khi thử tạo wrapper rõ ràng:

~~~java
new StandardMBean(
        new InvalidType(), InvalidTypeMXBean.class, true);
~~~

JDK24 đã ném `IllegalArgumentException` trong thử nghiệm vì không thể xây interface MXBean compliance hợp lệ. Đây là lý do **viết unit test cho việc đăng ký/construct wrapper**, không chỉ kiểm tên.

### 11.3. Getter/setter/operation naming rules

JMX coi interface methods theo các pattern sau:

- `T getN()`: thuộc tính readable tên `N`.
- `boolean isN()`: thuộc tính boolean readable tên `N`.
- `void setN(T value)`: thuộc tính writable tên `N`.
- Các methods khác: JMX operations, như `void clear()`.

Ví dụ:

~~~java
public interface CacheMXBean {
    int getSize();
    boolean isEnabled();
    void setEnabled(boolean value);
    void clear();
}
~~~

Như vậy expose attributes `Size` (read-only), `Enabled` (read/write) và operation `clear`.

Không tạo hai getters có cùng attribute name nhưng return types mâu thuẫn; getter/setter cho cùng attribute cần type tương thích theo JMX rules. Tránh overload methods khiến operation signatures khó quản trị; validate contract khi triển khai.

## 12. Đừng nhầm `JMX.isMXBeanInterface` với descriptor `mxbean`

Hai thứ phục vụ mục đích khác nhau:

- `JMX.isMXBeanInterface(Some.class)` hỏi **interface class này có được nhận diện theo quy tắc MXBean không?**
- `server.getMBeanInfo(name).getDescriptor().getFieldValue(JMX.MXBEAN_FIELD)` hỏi **instance đã đăng ký có metadata thể hiện là MXBean không?**

Để kiểm tra instance:

~~~java
Object raw = server.getMBeanInfo(name)
        .getDescriptor()
        .getFieldValue(JMX.MXBEAN_FIELD);

boolean actualMxBean =
        Boolean.parseBoolean(String.valueOf(raw));
~~~

`JMX.MXBEAN_FIELD` là hằng chuỗi của tên descriptor field `mxbean`. Đừng so cứng kiểu trả về luôn là `Boolean` hoặc luôn là `String` khi đọc descriptor của các providers khác nhau; nên validate metadata theo contract/app.

### 12.1. Tại sao test hai tham số cho kết quả khác?

~~~text
JMX.isMXBeanInterface(CacheMXBean.class)
    --> true                 (interface recognition)

new StandardMBean(new Cache(), CacheMXBean.class)
    --> Standard wrapper     (explicit wrapper constructor selection)

new StandardMBean(new Cache(), CacheMXBean.class, true)
    --> MXBean wrapper       (explicit MXBean selection)

server.registerMBean(new Cache(), name)
    --> MXBean via direct auto-detection
        when no Dynamic/Standard pattern wins
~~~

Tất cả 4 kết quả đã được kiểm bằng runnable program. Đây không phải mâu thuẫn API; các method làm **những công việc khác nhau**.

## 13. Truy cập MBean qua đúng loại proxy

Với một MXBean đã đăng ký:

~~~java
CacheMXBean proxy =
        JMX.newMXBeanProxy(server, name, CacheMXBean.class);

int count = proxy.getSize();
List<String> values = proxy.getTags();
proxy.clear();
~~~

Với Standard MBean:

~~~java
LegacyMXBean proxy =
        JMX.newMBeanProxy(server, name, LegacyMXBean.class);

String value = proxy.getValue();
~~~

`LegacyMXBean` cố ý có `@MXBean(false)` nhưng tên vẫn mang suffix. Nó được wrap thành Standard MBean để ví dụ cho thấy **khi chọn proxy, hãy dựa vào registered semantics**, không chỉ tên interface.

Một số cặp proxy/attribute với types đơn giản có thể tình cờ hoạt động dù bạn dùng nhầm helper; không suy ra rằng dùng sai proxy type luôn phát sinh exception. Với complex OpenData mapping, sự khác biệt có thể dẫn tới lỗi chuyển kiểu và contract sai. Hãy đăng ký, kiểm descriptor và dùng proxy tương ứng.

### 13.1. MBeanServer không tự mở kết nối mạng

Trong demo:

~~~java
MBeanServer server =
        MBeanServerFactory.createMBeanServer("demo");
~~~

Đây là **MBeanServer trong process**; tên domain `demo` không phải URL/host. `JMX.newMXBeanProxy(server,...)` tạo typed proxy nói chuyện với `MBeanServerConnection` tại chỗ.

**Không có JMX remote connector nào được tạo** nếu code không tự setup connector/port. Remote JMX management là cấu hình riêng; không nên mở management interface không có TLS/authentication/authorization.

## 14. Chương trình đầy đủ #1 — nhận diện và đăng ký MXBean

### 14.1. Mục tiêu kiểm thử

File `MxBeanRecognitionDemo.java` hoạt động độc lập trên Java 17+:

1. Kiểm tất cả 8 quy tắc nhận diện `JMX.isMXBeanInterface`.
2. Tạo MBeanServer trong JVM, **không mở JMX remote**.
3. Đăng ký `CacheMXBean` qua `StandardMBean(...,true)`, kiểm descriptor.
4. Đăng ký wrapper hai tham số cho cùng interface, chứng minh đó là Standard MBean.
5. Direct-register `new Cache()`, cho JMX tự phát hiện MXBean.
6. Đọc `List<String>` qua `MBeanServer.getAttribute` và nhận `String[]` OpenData.
7. Dùng MXBean typed proxy để đọc Size, Tags và gọi clear.
8. Đăng ký interface annotation không có suffix bằng explicit MXBean wrapper.
9. Đăng ký `@MXBean(false)` interface thành Standard MBean và dùng Standard proxy.
10. Thử một interface có return type `Object` không thể chuyển đổi.
11. Unregister mọi demo MBean và release MBeanServer trong `finally`.

Mọi dữ liệu là giả lập trong memory. Không sử dụng `ManagementFactory.getPlatformMBeanServer()` để tránh thay registry dùng chung của JVM; không tạo JMX remote connection.

### 14.2. Mã nguồn `MxBeanRecognitionDemo.java`

~~~java
import java.util.List;
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.MXBean;
import javax.management.ObjectName;
import javax.management.StandardMBean;

public final class MxBeanRecognitionDemo {
    public interface CacheMXBean {
        int getSize();
        List<String> getTags();
        void clear();
    }
    public static final class Cache implements CacheMXBean {
        private int size = 7;
        public int getSize() { return size; }
        public List<String> getTags() {
            return List.of("alpha", "beta");
        }
        public void clear() { size = 0; }
    }

    @MXBean
    public interface ServiceView {
        String getMode();
    }
    public static final class Service implements ServiceView {
        public String getMode() { return "safe"; }
    }

    @MXBean(true)
    public interface ActiveView {
        long getRequests();
    }

    @MXBean(false)
    public interface LegacyMXBean {
        String getValue();
    }
    public static final class Legacy implements LegacyMXBean {
        public String getValue() { return "std"; }
    }

    public interface OrdinaryView {
        int getNumber();
    }
    interface HiddenMXBean {
        int getX();
    }
    public static final class NotAnInterface { }
    public interface ChildView extends ServiceView { }

    public interface InvalidTypeMXBean {
        Object getAnything();
    }
    public static final class InvalidType
            implements InvalidTypeMXBean {
        public Object getAnything() {
            return new Object();
        }
    }

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    private static boolean descriptorMx(
            MBeanServer server, ObjectName name)
            throws Exception {
        Object raw = server.getMBeanInfo(name)
                .getDescriptor()
                .getFieldValue(JMX.MXBEAN_FIELD);
        return Boolean.parseBoolean(String.valueOf(raw));
    }

    public static void main(String[] args) throws Exception {
        require(JMX.isMXBeanInterface(CacheMXBean.class), "suffix");
        require(JMX.isMXBeanInterface(ServiceView.class), "marker");
        require(JMX.isMXBeanInterface(ActiveView.class), "true");
        require(!JMX.isMXBeanInterface(LegacyMXBean.class), "false");
        require(!JMX.isMXBeanInterface(OrdinaryView.class), "ordinary");
        require(!JMX.isMXBeanInterface(HiddenMXBean.class), "nonpublic");
        require(!JMX.isMXBeanInterface(NotAnInterface.class), "class");
        require(!JMX.isMXBeanInterface(ChildView.class), "child");

        System.out.println("Public suffix MXBean: true");
        System.out.println("Public @MXBean interface: true");
        System.out.println("Public @MXBean(true) interface: true");
        System.out.println("@MXBean(false) overrides suffix: true");
        System.out.println("Unannotated ordinary interface: false");
        System.out.println("Nonpublic suffix interface: false");
        System.out.println(
                "Concrete class is an MXBean interface: false");
        System.out.println(
                "Child interface without marker/suffix: false");

        MBeanServer mbs =
                MBeanServerFactory.createMBeanServer("demo");

        ObjectName cacheName =
                new ObjectName("demo.mx:type=Cache");
        ObjectName directName =
                new ObjectName("demo.mx:type=Direct");
        ObjectName twoArgName =
                new ObjectName("demo.mx:type=TwoArg");
        ObjectName serviceName =
                new ObjectName("demo.mx:type=Service");
        ObjectName legacyName =
                new ObjectName("demo.mx:type=Legacy");

        try {
            mbs.registerMBean(
                    new StandardMBean(
                            new Cache(), CacheMXBean.class, true),
                    cacheName);
            require(descriptorMx(mbs, cacheName), "wrapper MXBean");
            System.out.println(
                    "Explicit StandardMBean(...,true) is MXBean: true");

            mbs.registerMBean(
                    new StandardMBean(new Cache(), CacheMXBean.class),
                    twoArgName);
            require(!descriptorMx(mbs, twoArgName), "2-arg Standard");
            System.out.println(
                    "Two-argument StandardMBean is Standard: true");

            mbs.registerMBean(new Cache(), directName);
            require(descriptorMx(mbs, directName),
                    "automatic detection");
            System.out.println(
                    "Direct registration auto-detects MXBean: true");

            Object rawTags = mbs.getAttribute(cacheName, "Tags");
            require(rawTags instanceof String[], "List OpenType map");
            System.out.println(
                    "List<String> maps to String[] OpenType: true");

            CacheMXBean mxProxy =
                    JMX.newMXBeanProxy(
                            mbs, cacheName, CacheMXBean.class);
            require(mxProxy.getSize() == 7, "read");
            require(mxProxy.getTags().equals(
                    List.of("alpha", "beta")), "list reconstruction");
            mxProxy.clear();
            require(mxProxy.getSize() == 0, "operation");
            System.out.println(
                    "Typed MXBean proxy read/clear: true");

            mbs.registerMBean(
                    new StandardMBean(
                            new Service(), ServiceView.class, true),
                    serviceName);
            require(descriptorMx(mbs, serviceName), "annotation");
            require("safe".equals(
                    mbs.getAttribute(serviceName, "Mode")),
                    "attribute");
            System.out.println(
                    "Annotated no-suffix interface registers: true");

            mbs.registerMBean(
                    new StandardMBean(
                            new Legacy(), LegacyMXBean.class),
                    legacyName);
            require(!descriptorMx(mbs, legacyName),
                    "opt-out wrapper");
            LegacyMXBean stdProxy =
                    JMX.newMBeanProxy(
                            mbs, legacyName, LegacyMXBean.class);
            require("std".equals(stdProxy.getValue()),
                    "standard proxy");
            System.out.println(
                    "Opt-out interface uses Standard MBean proxy: true");

            boolean mappingRejected = false;
            try {
                new StandardMBean(
                        new InvalidType(),
                        InvalidTypeMXBean.class, true);
            } catch (IllegalArgumentException expected) {
                mappingRejected = true;
            }
            require(mappingRejected,
                    "invalid Object return type");
            System.out.println(
                    "Unsupported Object result mapping rejected: true");
        } finally {
            for (ObjectName name : new ObjectName[] {
                    cacheName, directName, twoArgName,
                    serviceName, legacyName }) {
                if (mbs.isRegistered(name)) {
                    mbs.unregisterMBean(name);
                }
            }
            MBeanServerFactory.releaseMBeanServer(mbs);
        }
        System.out.println(
                "Temporary MBeanServer released: true");
        System.out.println(
                "No JMX remote connector opened: true");
    }
}
~~~

### 14.3. Lệnh chạy

Lưu đúng tên file `MxBeanRecognitionDemo.java`:

~~~sh
javac --release 17 MxBeanRecognitionDemo.java
java MxBeanRecognitionDemo
~~~

Không cần thư viện ngoài hoặc JMX remote. Test đã biên dịch qua `javac --release 17` trên JDK24 và chạy thành công.

**Stdout chính xác gồm 18 dòng:**

~~~text
Public suffix MXBean: true
Public @MXBean interface: true
Public @MXBean(true) interface: true
@MXBean(false) overrides suffix: true
Unannotated ordinary interface: false
Nonpublic suffix interface: false
Concrete class is an MXBean interface: false
Child interface without marker/suffix: false
Explicit StandardMBean(...,true) is MXBean: true
Two-argument StandardMBean is Standard: true
Direct registration auto-detects MXBean: true
List<String> maps to String[] OpenType: true
Typed MXBean proxy read/clear: true
Annotated no-suffix interface registers: true
Opt-out interface uses Standard MBean proxy: true
Unsupported Object result mapping rejected: true
Temporary MBeanServer released: true
No JMX remote connector opened: true
~~~

### 14.4. Diễn giải kết quả theo từng nhóm

**8 dòng đầu:** Quy tắc interface: suffix/annotation true được nhận; annotation false, interface không public, class thường và child interface không tự có annotation/suffix không được nhận.

**Explicit wrapper và two-arg wrapper:** Cùng một `CacheMXBean` nhưng `StandardMBean(..., true)` tạo MXBean; `StandardMBean(object, interface)` tạo Standard MBean. Đây là bằng chứng **tên hợp lệ không tự áp cho mọi wrapper constructor**.

**Direct registration:** Khi gọi `registerMBean(new Cache(), name)`, implementation class `Cache` không có Standard MBean interface `CacheMBean`, nhưng implements một MXBean interface `CacheMXBean`, nên auto-detection chọn MXBean.

**List mapping:** `List<String>` trong Java interface được MBeanServer hiển thị thành `String[]`, đúng OpenType; typed proxy chuyển lại thành `List<String>`.

**@MXBean without suffix:** `ServiceView` được wrap với `true` và đăng ký thành MXBean thành công; getter `getMode()` trả `Mode`.

**Opt-out Standard MBean:** `LegacyMXBean` bị `@MXBean(false)` loại khỏi auto-recognition, nhưng vẫn là một Java interface hợp lệ để `StandardMBean` wrapper xuất như Standard; cần `newMBeanProxy` khi muốn theo Standard semantics.

**Invalid Java type:** `Object getAnything()` không tự ánh xạ thành một OpenType tùy ý, nên constructor yêu cầu MXBean semantics bị từ chối.

**Cleanup:** Demo dùng MBeanServer tạm, unregister trong `finally` và release server, không chạm tới platform MBeanServer hay JMX remote configuration.

## 15. Chương trình đầy đủ #2 — thứ tự ưu tiên và nhiều candidates

Ví dụ `MxBeanSelectionDemo.java` bổ sung các quy tắc mà `JMX.isMXBeanInterface` đơn lẻ không thể chứng minh: ưu tiên Standard naming khi direct register; chọn interface con cụ thể nhất; reject nhiều MXBeans không có quan hệ kế thừa; explicit wrapper `isMXBean=true`.

### 15.1. Mã nguồn `MxBeanSelectionDemo.java`

~~~java
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.MXBean;
import javax.management.NotCompliantMBeanException;
import javax.management.ObjectName;
import javax.management.StandardMBean;

public final class MxBeanSelectionDemo {
    public interface DualMBean {
        int getStandard();
    }
    public interface DualMXBean {
        int getMx();
    }
    public static final class Dual
            implements DualMBean, DualMXBean {
        public int getStandard() { return 3; }
        public int getMx() { return 9; }
    }

    public interface LeftMXBean {
        int getLeft();
    }
    public interface RightMXBean {
        int getRight();
    }
    public static final class Ambiguous
            implements LeftMXBean, RightMXBean {
        public int getLeft() { return 1; }
        public int getRight() { return 2; }
    }

    public interface BaseMXBean {
        int getCount();
    }
    public interface ExtendedMXBean extends BaseMXBean {
        String getName();
    }
    public static final class Extended
            implements ExtendedMXBean {
        public int getCount() { return 7; }
        public String getName() { return "child"; }
    }

    @MXBean(false)
    public interface OptOutMXBean {
        int getValue();
    }
    public static final class OptOut
            implements OptOutMXBean {
        public int getValue() { return 11; }
    }

    private static boolean isMX(
            MBeanServer mbs, ObjectName name)
            throws Exception {
        return Boolean.parseBoolean(String.valueOf(
                mbs.getMBeanInfo(name)
                        .getDescriptor()
                        .getFieldValue(JMX.MXBEAN_FIELD)));
    }

    private static void require(
            boolean value, String message) {
        if (!value) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args)
            throws Exception {
        MBeanServer mbs =
                MBeanServerFactory.createMBeanServer("priority");
        ObjectName dualName =
                new ObjectName("priority:type=Dual");
        ObjectName extendedName =
                new ObjectName("priority:type=Extended");
        ObjectName ambiguousName =
                new ObjectName("priority:type=Ambiguous");
        ObjectName forcedName =
                new ObjectName("priority:type=Forced");

        try {
            mbs.registerMBean(new Dual(), dualName);
            require(!isMX(mbs, dualName),
                    "Standard priority");
            require(Integer.valueOf(3).equals(
                    mbs.getAttribute(dualName, "Standard")),
                    "Standard attr");
            System.out.println(
                    "Standard MBean name takes precedence: true");

            mbs.registerMBean(
                    new Extended(), extendedName);
            require(isMX(mbs, extendedName),
                    "most specific MXBean");
            require("child".equals(
                    mbs.getAttribute(extendedName, "Name")),
                    "most-specific operation missing");
            System.out.println(
                    "Most specific subinterface selected: true");

            boolean ambiguousRejected = false;
            try {
                mbs.registerMBean(
                        new Ambiguous(), ambiguousName);
            } catch (NotCompliantMBeanException expected) {
                ambiguousRejected = true;
            }
            require(ambiguousRejected,
                    "Ambiguous interfaces accepted");
            System.out.println(
                    "Unrelated multiple MXBeans rejected: true");

            mbs.registerMBean(
                    new StandardMBean(
                            new OptOut(),
                            OptOutMXBean.class, true),
                    forcedName);
            require(isMX(mbs, forcedName),
                    "Forced MXBean wrapper");
            System.out.println(
                    "Explicit isMXBean=true overrides auto opt-out: true");
        } finally {
            for (ObjectName name : new ObjectName[] {
                    dualName, extendedName,
                    ambiguousName, forcedName }) {
                if (mbs.isRegistered(name)) {
                    mbs.unregisterMBean(name);
                }
            }
            MBeanServerFactory.releaseMBeanServer(mbs);
        }
        System.out.println(
                "All demo registrations cleaned: true");
    }
}
~~~

### 15.2. Biên dịch và đầu ra

~~~sh
javac --release 17 MxBeanSelectionDemo.java
java MxBeanSelectionDemo
~~~

**Stdout chính xác**, đã kiểm bằng Java17 source compatibility trên JDK24:

~~~text
Standard MBean name takes precedence: true
Most specific subinterface selected: true
Unrelated multiple MXBeans rejected: true
Explicit isMXBean=true overrides auto opt-out: true
All demo registrations cleaned: true
~~~

Các test này cho thấy **quy tắc chọn implementation khi đăng ký** là tầng khác với `JMX.isMXBeanInterface`. Một interface đơn lẻ có thể là MXBean candidate nhưng object implements nhiều candidates khác nhau sẽ không đăng ký tự động được nếu không có một candidate con cụ thể nhất.

### 15.3. Tại sao chỉ test annotation suffix chưa đủ?

Nếu chỉ viết:

~~~java
assert JMX.isMXBeanInterface(DualMXBean.class);
~~~

Bạn có thể nhầm rằng direct-register `new Dual()` sẽ là MXBean. Trên thực tế, vì `Dual` implements `DualMBean` theo naming convention **Standard MBean** tương ứng implementation class name, nhánh Standard thắng. Phải kiểm `MBeanInfo` của object đã được đăng ký.

## 16. Chọn auto-detection hay explicit wrapper trong dự án thật?

### 16.1. Auto-detection khi hợp đồng đơn giản

~~~java
server.registerMBean(
        new Cache(),
        new ObjectName("example:type=Cache"));
~~~

Đây là snippet sử dụng class `Cache` implements `CacheMXBean`. Hãy đảm bảo class không đồng thời tuân theo một Standard MBean naming pattern khác và không có nhiều MXBean candidates mơ hồ.

### 16.2. Explicit wrapper khi muốn deterministic

~~~java
server.registerMBean(
        new StandardMBean(
                new Cache(), CacheMXBean.class, true),
        new ObjectName("example:type=Cache"));
~~~

`true` làm rõ lựa chọn MXBean. Khi code review, người đọc có thể thấy ngay semantics mà không cần suy ngược interface names, parent interfaces hoặc ưu tiên Standard MBean naming.

### 16.3. Lựa chọn proxy phải khớp cách đăng ký

- MXBean → `JMX.newMXBeanProxy(...)` khi cần typed proxy và OpenType conversions.
- Standard MBean → `JMX.newMBeanProxy(...)`.
- Công cụ generic → đọc `MBeanInfo` và `Descriptor`, truy cập `MBeanServerConnection` bằng `getAttribute`/`invoke`.

Đối với MXBean có references sang MXBeans khác hoặc nested composites, kiểm kỹ mapping và type reconstruction. Không dựa vào một phép đọc `String` thành công để suy luận mọi kiểu dữ liệu sẽ hoạt động.

## 17. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `JMX.isMXBeanInterface(...) == false` | Interface không public | Khai báo management interface public |
| `false` dù tên chứa MXBean | Suffix không ở cuối hoặc sai chữ hoa | Đặt tên chính xác `...MXBean` |
| `false` dù tên kết thúc MXBean | Có `@MXBean(false)` | Kiểm annotation rõ ràng |
| `false` trên interface con | Annotation cha không tự đánh dấu interface con | Gắn annotation/convention cho con |
| `false` trên class | Đối số không phải interface | Truyền `SomeMXBean.class` |
| `NullPointerException` | Truyền null cho JMX.isMXBeanInterface | Không truyền null |
| Instance có descriptor `mxbean=false` | Đăng ký Standard MBean, hai-arg wrapper hoặc Standard priority | Kiểm cách đăng ký và constructor flag |
| Direct registration chọn Standard | Implementation phù hợp `ClassNameMBean` | Dùng explicit MXBean wrapper nếu muốn |
| Direct registration bị từ chối | Multiple unrelated MXBeans | Chọn interface cụ thể nhất hoặc explicit wrapper |
| Direct registration bị từ chối | Không có management interface hợp lệ | Kiểm public interface và convention |
| Wrapper không tạo được | Object không implements interface đã chọn | Sửa contract/class |
| MXBean construction ném lỗi | Java method type không OpenType-mappable | Thiết kế DTO/record/collection có mapping hợp lệ |
| Getter/attribute không xuất hiện | Tên method sai `getN/isN/setN` hoặc interface chọn sai | Xem MBeanInfo attributes/operations |
| Client nhận `String[]` thay vì List | Đọc raw OpenData MXBean | Dùng typed MXBean proxy hoặc xử lý OpenData |
| Proxy lỗi conversion | Proxy type không khớp registered MXBean/Standard, type reconstruction sai | Kiểm descriptor và mapping |
| Standard MBean xuất custom object khó dùng remote | Không có OpenData conversion | Chuyển sang MXBean hợp lệ |
| Registered ObjectName trùng | Đã có MBean cùng tên | Unregister/đặt ObjectName unique theo policy |
| MBeanServer vẫn giữ object sau test | Quên unregister | `finally` + `unregisterMBean` |
| Kiểm nhầm platform server | Dùng ManagementFactory.getPlatformMBeanServer ngoài ý muốn | Dùng MBeanServerFactory tạo local test server |
| Remote JMX không truy cập được | Chưa thiết lập JMX connector | Local registration không mở remote endpoint |
| Remote JMX bị lộ | Mở connector không có auth/TLS/network ACL | Bảo vệ management port, phân quyền |

**Lưu ý exception:** Trong test, explicit `StandardMBean(..., true)` với kiểu không mappable báo `IllegalArgumentException`. Direct `MBeanServer.registerMBean` với interface mơ hồ báo `NotCompliantMBeanException`. Tên exception chính xác và thời điểm lỗi còn phụ thuộc đường API, provider/JDK; đừng dùng một loại exception duy nhất làm tiêu chí quyết định policy.

## 18. An toàn khi sử dụng MXBean: nhận diện không phải access control

MXBean là **management interface**. Một getter hoặc operation được export có thể tiết lộ dữ liệu hoặc thực hiện hành động, ví dụ reset counters, flush cache, thay config. Hãy:

1. Chỉ export attributes/operations được phê duyệt; không đưa secrets, credentials, access tokens, raw customer data.
2. Phân biệt read-only metrics với operations gây side effects.
3. Nếu dùng `MBeanServer` từ các modules trong cùng JVM, hiểu phạm vi truy cập nội bộ; đừng coi suffix tên là security boundary.
4. Không mở JMX remote connector công khai nếu chưa có authentication, authorization, TLS và network ACL.
5. Không cho client tùy ý chọn `ObjectName` hoặc operation name mà không có kiểm tra quyền ở service layer.
6. Chú ý DoS: expensive getters/operations có thể gây tắc nghẽn JMX monitoring threads.
7. Không trả về mutable internal collections khiến state bị lộ hoặc bị thay đổi ngoài contract; MXBean OpenData mapping là chuyển kiểu, **không tự là chính sách bảo mật**.
8. Khi export cấu trúc phức tạp, kiểm các fields/keys có tiết lộ topology, dữ liệu nội bộ hoặc thông tin nhận dạng người dùng hay không.
9. Đóng unregister/connection resources trong shutdown/test lifecycle; không tạo tràn MBean instances.

**`@MXBean(false)` không bảo vệ một interface khỏi đăng ký theo `StandardMBean(..., true)` nếu caller có quyền làm vậy.** Để hạn chế access phải dùng quản lý MBeanServer/connector và authorization, không dựa vào annotation naming.

## 19. Test matrix nên có cho nhận diện MXBean

| Trường hợp | Thiết kế test | Kết quả mong đợi |
| --- | --- | --- |
| Public interface có suffix | `CacheMXBean` | `isMXBeanInterface == true` |
| Public interface có `@MXBean` | `ServiceView` | `true` |
| Public interface có `@MXBean(true)` | `ActiveView` | `true` |
| Public interface có `@MXBean(false)` và suffix | `LegacyMXBean` | `false` |
| Public interface không suffix/annotation | `OrdinaryView` | `false` |
| Interface không public có suffix | `HiddenMXBean` | `false` |
| Concrete class | `NotAnInterface.class` | `false` |
| Interface con không annotation/suffix | `ChildView` extends annotated | `false` với chính ChildView |
| Null Class argument | `JMX.isMXBeanInterface(null)` | `NullPointerException` |
| Direct register một MXBean candidate | `new Cache()` | Descriptor MXBean true |
| Direct register class có Standard pattern | `Dual implements DualMBean, DualMXBean` | Standard được chọn |
| Direct register nhiều candidates có subtype | `ExtendedMXBean extends BaseMXBean` | Chọn subtype |
| Direct register nhiều unrelated candidates | `LeftMXBean + RightMXBean` | `NotCompliantMBeanException` |
| Two-argument wrapper | `new StandardMBean(cache, CacheMXBean.class)` | Standard descriptor |
| Explicit MXBean wrapper | `new StandardMBean(cache, CacheMXBean.class, true)` | MXBean descriptor |
| Explicit opt-out override | `@MXBean(false)` nhưng wrapper flag true | MXBean nếu types hợp lệ |
| Standard opt-out registration | `new StandardMBean(legacy, LegacyMXBean.class)` | Standard proxy đọc được |
| OpenType mapping | `List<String> getTags()` | Raw `String[]`, typed proxy `List<String>` |
| Unsupported type | `Object getAnything()` | MXBean construction bị từ chối |
| Getter naming | `getSize()` | Attribute `Size` |
| Operation naming | `clear()` | Operation `clear` |
| Proxy semantics | `JMX.newMXBeanProxy` | Đọc và gọi operation đúng |
| Descriptor metadata | `JMX.MXBEAN_FIELD` | Nhận diện loại đã đăng ký |
| Existing ObjectName | Đăng ký trùng | Reject/handle already-exists |
| Cleanup | `unregisterMBean`/release | Không để dư demo MBeans |
| Remote management | Không mở JMXConnector | Không có remote listener từ unit tests |
| Java17 compatibility | `javac --release 17` | Hai demos biên dịch và chạy |

**Test checklist thực tế:** Kiểm cả interface classification, object registration, MBeanInfo metadata, OpenType data readback và typed proxy. Không chỉ test naming.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Một interface public có tên `CacheMXBean` có cần `@MXBean` không?

**Trả lời:** Không, nếu không có annotation cản trở. Hậu tố `MXBean` tự đủ để nhận diện interface theo convention.

**Câu 2.** `@MXBean` khác `@MXBean(true)` thế nào?

**Trả lời:** Về ý nghĩa nhận diện thì tương đương; giá trị mặc định của annotation là true.

**Câu 3.** `@MXBean(false)` trên `LegacyMXBean` làm gì?

**Trả lời:** Nó ngăn auto-recognition là MXBean interface dù tên có hậu tố `MXBean`.

**Câu 4.** Interface không public nhưng tên đúng suffix có được nhận diện không?

**Trả lời:** Không. Quy tắc JavaDoc yêu cầu public interface.

**Câu 5.** `ChildView extends ServiceView` có tự nhận `@MXBean` của ServiceView không?

**Trả lời:** Không; nếu ChildView không có annotation hoặc suffix, `JMX.isMXBeanInterface(ChildView.class)` vẫn false.

**Câu 6.** `JMX.isMXBeanInterface` có tự tạo MXBean instance không?

**Trả lời:** Không. Đây là check trên `Class<?>`, không tạo/register MBean.

**Câu 7.** Vì sao `new StandardMBean(cache, CacheMXBean.class)` có thể là Standard MBean?

**Trả lời:** Vì constructor hai tham số chọn Standard MBean semantics. Nếu muốn MXBean wrapper, dùng constructor có `isMXBean=true`.

**Câu 8.** Direct register một class implements `ClassNameMBean` và `ClassNameMXBean` sẽ ưu tiên gì?

**Trả lời:** Theo JavaDoc, Standard MBean naming được xét trước MXBean candidates, nên Standard MBean có thể thắng.

**Câu 9.** Nếu class implements hai MXBean interfaces không liên quan, direct registration ra sao?

**Trả lời:** Không có một interface duy nhất hoặc subtype của tất cả, nên đăng ký bị từ chối. Chọn interface quản trị rõ ràng/explicit wrapper.

**Câu 10.** Nếu một interface con extends interface MXBean cha, direct registration có thể chọn con không?

**Trả lời:** Có khi con cũng là MXBean candidate và là subinterface của các candidates khác. Đây là rule chọn nhiều interfaces, không phải annotation tự được kế thừa.

**Câu 11.** `Object getAnything()` có phải một type MXBean hợp lệ mặc định?

**Trả lời:** Không. MXBean phải chuyển Java types sang Open Types; Object tùy ý không có mapping tổng quát.

**Câu 12.** Vì sao raw JMX nhận `String[]` khi interface khai báo `List<String>`?

**Trả lời:** MXBean ánh xạ List<String> thành OpenType array String[] để công cụ generic đọc được.

**Câu 13.** Dùng proxy nào cho MXBean?

**Trả lời:** `JMX.newMXBeanProxy(...)`; cho Standard MBean dùng `JMX.newMBeanProxy(...)` theo semantics đã đăng ký.

**Câu 14.** Làm sao xác nhận một instance là MXBean sau khi register?

**Trả lời:** Xem `MBeanInfo.getDescriptor().getFieldValue(JMX.MXBEAN_FIELD)` (hoặc OpenMBeanInfo metadata) thay vì chỉ suy luận từ interface name.

**Câu 15.** `ObjectName` phải có suffix `MXBean` không?

**Trả lời:** Không. ObjectName là danh tính MBean instance (domain/key properties), không phải tên management interface class.

**Câu 16.** Có cần mở JMX remote port để unit test registration không?

**Trả lời:** Không. MBeanServer cục bộ đủ để kiểm nhận diện, OpenTypes, proxy và operations.

**Câu 17.** `@MXBean(false)` có ngăn caller tạo wrapper `StandardMBean(...,true)` không?

**Trả lời:** Không; explicit isMXBean flag quyết định wrapper semantics nếu interface đáp ứng compliance. Không dùng annotation này làm cơ chế phân quyền.

**Câu 18.** Một getter chạy rất tốn CPU có an toàn vì nằm trong MXBean không?

**Trả lời:** Không. MXBean chỉ quyết định management representation, không tự thêm CPU timeout, quotas hoặc authorization.

**Câu 19.** Khi nào cần kiểm registration failures trong CI?

**Trả lời:** Khi thay methods, return/parameter types, inheritance hoặc annotation; luôn kiểm OpenType mapping và proxy, không chỉ `isMXBeanInterface`.

**Câu 20.** Nguyên tắc quan trọng nhất là gì?

**Trả lời:** **Public + suffix/annotation quyết định nhận diện interface; registration path chọn Standard/MXBean, type mapping quyết định compliance.** Kiểm đủ cả ba lớp.

**Ghi nhớ:** Một interface được JMX nhận diện là MXBean khi **public** và (tên kết thúc `MXBean` mà không bị `@MXBean(false)`, hoặc có `@MXBean`/`@MXBean(true)`). Annotation không tự đánh dấu interface con; JMX auto-registration ưu tiên Dynamic/Standard patterns trước rồi mới chọn một MXBean candidate hoặc subtype cụ thể nhất. `StandardMBean(impl, interface)` là Standard wrapper, còn `StandardMBean(impl, interface, true)` là MXBean wrapper. Sau đó vẫn cần OpenType mapping hợp lệ, đăng ký thành công, đúng `MBeanInfo` và proxy phù hợp. **Nhận diện theo tên không thay cho tính hợp lệ hoặc bảo mật JMX.**

### Tài liệu chính thức, vẫn được áp dụng

- [Oracle Java SE 26 — MXBean annotation và MXBean specification](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MXBean.html): public/naming/annotation, direct-registration priority, OpenType mapping, method naming.
- [Oracle Java SE 26 — JMX](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/JMX.html): `isMXBeanInterface`, MXBean/Standard proxies và descriptor constants.
- [Oracle Java SE 26 — StandardMBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/StandardMBean.html): wrapper constructors, `isMXBean` flag, compliance.
- [Oracle Java SE 26 — MBeanServer](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServer.html): register/unregister, access to attributes/operations.
- [Oracle Java SE 26 — MBeanInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanInfo.html): metadata của registered MBean.
- [Oracle Java SE 26 — OpenType](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/OpenType.html): các dạng OpenType.
- [Oracle Java SE 26 — CompositeData](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeData.html): OpenData cho kiểu phức tạp.
- [Oracle Java SE 17 — MXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MXBean.html): API hiện diện trên Java 17 LTS.
