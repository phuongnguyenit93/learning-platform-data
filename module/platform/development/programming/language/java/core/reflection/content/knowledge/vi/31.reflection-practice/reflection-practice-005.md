# Thực hành: Xây dựng bộ ánh xạ dữ liệu nhỏ qua accessor hoặc record component

## 1. Bài toán và kết quả mong muốn

Giả sử ứng dụng cần chuyển một object Java thành một bảng dữ liệu có dạng `Map<String, Object>`. Bảng đó có thể phục vụ logging có kiểm soát, tạo dữ liệu hiển thị, chuyển sang một DTO khác hoặc làm bước đầu cho serialization. Với các lớp đã biết từ trước, một method chuyển đổi tường minh thường là lựa chọn đơn giản nhất; bài thực hành này tập trung vào trường hợp **cần khám phá cấu trúc ở runtime bằng Reflection**, nhưng vẫn phải giới hạn phạm vi và xử lý lỗi rõ ràng.

Ta sẽ viết một bộ ánh xạ **một chiều**:

```text
Java object
    |
    |-- record?  --> RecordComponent[] --> getAccessor() --> Method.invoke(...)
    |
    +-- JavaBean? --> PropertyDescriptor[] --> getReadMethod() --> Method.invoke(...)
    |
    v
Map<String, Object>  (khóa = tên thành phần/property, giá trị = kết quả accessor)
```

Đầu vào ví dụ gồm:

- `Invoice` là **record** với hai thành phần `code` và `total`.
- `CustomerView` là **class kiểu JavaBean đọc được** với getter `getName()` và `isActive()`.
- Bộ ánh xạ nhận **duy nhất hai kiểu đã được cho phép**; không tự đọc bất kỳ class nào do người dùng gửi tên.
- Bản đồ kết quả sắp xếp theo tên khóa cho dễ kiểm thử và không cho sửa qua API `Map` trả về.

Kết quả dự kiến:

```text
record = {code=INV-7, total=80}
bean = {active=true, name=Lan}
```

**Phạm vi cố ý nhỏ:** chỉ đọc thuộc tính top-level, giữ nguyên giá trị kiểu Java; không đọc trực tiếp private field, không dựng object từ map, không đi vào object lồng nhau, không xử lý cycle, không tự động chuyển kiểu và **không tạo JSON**. `Map.toString()` là biểu diễn in thử trong Java, không phải JSON hợp lệ.

## 2. Hiểu hai kiểu accessor trước khi viết mapper

### Record component

Từ Java 16, record là cú pháp mô tả một dạng class được thiết kế để mang dữ liệu với tập component xác định. Ví dụ:

```java
public record Invoice(String code, int total) {}
```

Compiler cung cấp các accessor tương ứng: `code()` và `total()`. Chúng **không phải JavaBeans getter tên `getCode()` hay `getTotal()`**. Vì vậy không nên mặc định JavaBeans Introspector sẽ tìm đúng property của record.

Reflection cung cấp:

- `type.isRecord()`: kiểm tra class có phải record.
- `type.getRecordComponents()`: lấy các `RecordComponent` được khai báo, theo thứ tự component trong header.
- `component.getName()`: tên component, ví dụ `"code"`.
- `component.getType()`: kiểu khai báo, ví dụ `String.class` hoặc `int.class`.
- `component.getAccessor()`: đối tượng `Method` của accessor tương ứng; có thể gọi bằng `Method.invoke(receiver)`.

Ví dụ khái niệm:

```java
RecordComponent[] parts = Invoice.class.getRecordComponents();
for (RecordComponent part : parts) {
    Method accessor = part.getAccessor();
    // Object value = accessor.invoke(invoice);
}
```

Đây là **đoạn mã minh họa cần import và khai báo ngữ cảnh**, không phải file chạy riêng. Kiểu primitive như `int` được boxing thành `Integer` khi lưu dưới kiểu `Object` trong map.

Record thường tạo các field final/private và accessor public; mapper sử dụng accessor **thay vì** bật quyền truy cập private field. Tuy nhiên tính “bất biến nông” của record không bảo đảm dữ liệu tham chiếu bên trong bất biến: nếu component chứa `List` có thể thay đổi, map sẽ giữ reference đến cùng đối tượng list.

### JavaBean property

Với class thông thường:

```java
public static final class CustomerView {
    private final String name;
    private final boolean active;

    public CustomerView(String name, boolean active) {
        this.name = name;
        this.active = active;
    }

    public String getName() { return name; }
    public boolean isActive() { return active; }
}
```

Theo quy ước JavaBeans:

- `getName()` đại diện cho property `name`.
- `isActive()` đại diện cho property boolean `active`.
- Property chỉ đọc **vẫn hợp lệ** dù class không có setter.
- Method tùy ý `calculate()` không tự nhiên là JavaBean property.
- `getClass()` được kế thừa từ `Object`; không nên đưa metadata class nội bộ vào bản đồ dữ liệu.

`java.beans.Introspector.getBeanInfo(type, Object.class)` khám phá thuộc tính theo quy ước và loại bỏ phần thông tin thuộc superclass `Object`. Mỗi `PropertyDescriptor` có `getName()`, `getPropertyType()` và `getReadMethod()`. Method đọc có thể null nếu property chỉ ghi; mapper bỏ qua trường hợp đó.

Khác với record component, JavaBean là một **quy ước đặt tên và metadata**, không phải một cú pháp class bắt buộc. Tên property không nhất thiết giống tên field: một getter có thể tính giá trị thay vì đọc trực tiếp field, và có thể có tác dụng phụ hoặc ném ngoại lệ.

**Thông tin module:** `java.beans.Introspector` thuộc module JDK `java.desktop`, không thuộc `java.base`. Ở ứng dụng có file `module-info.java`, cần `requires java.desktop;` khi dùng API JavaBeans này; ứng dụng trên classpath thông thường với một JDK đầy đủ không cần khai báo đó.

## 3. Hợp đồng cụ thể của mini mapper

Ta chọn interface sử dụng đơn giản:

```java
Map<String, Object> toMap(Object source);
```

Hợp đồng:

1. `source == null` bị từ chối bằng `NullPointerException` với thông báo `"source"`.
2. Kiểu source được kiểm tra theo **allowlist** gồm `Invoice.class` và `CustomerView.class`; kiểu khác bị từ chối bằng `IllegalArgumentException`. Điều này giữ Reflection trong phạm vi kiểm soát.
3. Với record, chỉ lấy component do `getRecordComponents()` trả về và gọi accessor tương ứng.
4. Với JavaBean, chỉ lấy readable property từ `PropertyDescriptor` do Introspector trả về, không tìm field private.
5. Getter có thể thất bại. Mapper **không nuốt lỗi** mà báo `IllegalStateException` và giữ `cause` gốc.
6. Giá trị `null` được phép giữ trong map vì dùng `TreeMap` (không dùng `Map.copyOf`, vốn không cho phép null).
7. Kết quả được bao bởi `Collections.unmodifiableMap(...)`. Caller không thêm, xóa hoặc thay entry qua map đó; điều này không làm bất biến sâu các object được lưu làm value.

Bài này dùng khóa tên property (`String`) nên không có key null. Thứ tự key của `TreeMap` là thứ tự tự nhiên của chuỗi, không phải thứ tự khai báo record hay thứ tự Reflection/Introspector trả về.

## 4. Chương trình hoàn chỉnh chạy được trên Java 17+

Tạo file **`TinyMapperDemo.java`**, nội dung:

```java
import java.beans.IntrospectionException;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public class TinyMapperDemo {
    public record Invoice(String code, int total) {}

    public static final class CustomerView {
        private final String name;
        private final boolean active;

        public CustomerView(String name, boolean active) {
            this.name = name;
            this.active = active;
        }

        public String getName() {
            return name;
        }

        public boolean isActive() {
            return active;
        }
    }

    public static Map<String, Object> toMap(Object source) {
        Objects.requireNonNull(source, "source");
        Class<?> type = source.getClass();

        // Không thực thi getter tùy ý trên class từ nguồn không tin cậy.
        if (type != Invoice.class && type != CustomerView.class) {
            throw new IllegalArgumentException(
                    "Unsupported: " + type.getName());
        }

        Map<String, Object> result = new TreeMap<>();

        if (type.isRecord()) {
            for (RecordComponent component : type.getRecordComponents()) {
                result.put(
                        component.getName(),
                        read(component.getAccessor(), source));
            }
        } else {
            try {
                for (PropertyDescriptor property :
                        Introspector.getBeanInfo(type, Object.class)
                                .getPropertyDescriptors()) {
                    Method accessor = property.getReadMethod();
                    if (accessor != null) {
                        result.put(property.getName(),
                                read(accessor, source));
                    }
                }
            } catch (IntrospectionException ex) {
                throw new IllegalStateException(
                        "Invalid bean metadata", ex);
            }
        }

        return Collections.unmodifiableMap(result);
    }

    private static Object read(Method accessor, Object receiver) {
        try {
            return accessor.invoke(receiver);
        } catch (IllegalAccessException ex) {
            throw new IllegalStateException(
                    "Inaccessible: " + accessor.getName(), ex);
        } catch (InvocationTargetException ex) {
            throw new IllegalStateException(
                    "Accessor failed: " + accessor.getName(),
                    ex.getCause());
        }
    }

    public static void main(String[] args) {
        System.out.println("record = "
                + toMap(new Invoice("INV-7", 80)));
        System.out.println("bean = "
                + toMap(new CustomerView("Lan", true)));
    }
}
```

Biên dịch và chạy từ đúng thư mục chứa file:

```bash
javac -encoding UTF-8 TinyMapperDemo.java
java TinyMapperDemo
```

Kết quả:

```text
record = {code=INV-7, total=80}
bean = {active=true, name=Lan}
```

Vì sao kết quả như trên?

**Với record** `new Invoice("INV-7", 80)`: `isRecord()` trả `true`, vòng lặp lấy hai component `code` và `total`. `getAccessor()` lần lượt dẫn tới `code()` trả `"INV-7"` và `total()` trả `80`. `TreeMap` giữ key theo alphabet nên hiển thị `code` trước `total`.

**Với JavaBean** `new CustomerView("Lan", true)`: kiểu này không phải record nên dùng `Introspector`. `getName()` được đọc thành `name=Lan` và `isActive()` thành `active=true`. Ta chỉ thu nhận readable properties, không thu `class` từ `Object.getClass()` nhờ dùng stop class `Object.class`. `TreeMap` sắp xếp `active` trước `name`.

**Tại sao `read(...)` dùng hai catch khác nhau?** Khi caller không đủ quyền, `Method.invoke` có thể ném `IllegalAccessException`. Khi accessor **được gọi** và tự ném exception, Reflection bọc exception ấy trong `InvocationTargetException`; `getCause()` truy ra lỗi bên trong. Mapper bọc lại bằng `IllegalStateException`, thay vì trả một map thiếu key khiến bug bị che giấu.

Các class trong ví dụ là nested type public và các accessor public; không cần `setAccessible(true)`. Với class/module khác, package visibility/module export có thể làm cho một method trông public nhưng không truy cập được từ caller. Đừng biến `setAccessible(true)` thành giải pháp mặc định.

## 5. Đọc kỹ luồng ánh xạ

### Bước 1: quyết định loại metadata

`type.isRecord()` là kiểm tra chuyên biệt dành cho record. Khi `true`, dùng `getRecordComponents()` thay vì đoán tên `getXxx()`. Khi `false`, bài này dùng quy ước JavaBeans cho một kiểu cho phép.

Đây là **hai đường ánh xạ riêng**. Không nên trộn một cách tự phát, ví dụ với record vừa lấy `getRecordComponents()` vừa quét `getMethods()` để tự đoán thêm thuộc tính: dễ gây key trùng hoặc gọi những method không thuộc hợp đồng dữ liệu.

### Bước 2: chỉ giữ accessor có thể gọi

Với record, `RecordComponent.getAccessor()` trả method accessor tương ứng. Với JavaBean, `PropertyDescriptor.getReadMethod()` có thể null nên cần kiểm tra.

Không trực tiếp lấy mọi `Method` theo `getMethods()` rồi tự bỏ tiền tố `get` vì dễ xử lý sai `isXxx`, thuộc tính viết hoa, property chỉ ghi, overload và các chi tiết quy ước JavaBeans. Introspector đã thực hiện một phần quan trọng của việc phân giải quy ước này.

### Bước 3: invoke với receiver đúng

Cả accessor record và JavaBean getter ở đây là **instance method không có đối số**:

```java
Object value = accessor.invoke(source);
```

Đoạn này minh họa khi đã có biến `accessor: Method` và `source`. Đối số `source` là receiver, không phải tham số getter. Nếu receiver sai kiểu, invocation sẽ lỗi. Giá trị kiểu primitive như `int`/`boolean` được boxing khi trả về dưới dạng `Object`.

### Bước 4: tạo map theo tên thuộc tính

Tên của record component đến từ `getName()`. Tên JavaBean property đến từ `PropertyDescriptor.getName()`, **không cần** tự viết thuật toán xóa `get`/`is` rồi lower-case.

Map sử dụng `TreeMap<String,Object>` để có thứ tự hiển thị ổn định. Khi serializer thực tế cần giữ thứ tự khai báo record, `LinkedHashMap` là lựa chọn hợp lý hơn; đầu ra của chương trình mẫu thì chủ ý **sắp xếp alphabet** để làm test rõ ràng.

### Bước 5: trả map không cho sửa trực tiếp

`Collections.unmodifiableMap(result)` làm người dùng không thể thao tác `put/remove` trên map trả về. Lưu ý nếu các value là list/map/object mutable, việc mutate bên trong value vẫn có thể xảy ra. Nếu cần snapshot bất biến sâu để chia sẻ đa luồng hoặc lưu trữ lâu dài, phải định nghĩa cách copy/serialize phù hợp, không mặc định wrapper map làm được việc đó.

## 6. Thử lỗi và kiểm tra hợp đồng

Với chương trình hoàn chỉnh ở trên, có thể thêm các lệnh sau **vào cuối `main`** để kiểm tra nhánh lỗi:

```java
try {
    toMap(new Object());
} catch (IllegalArgumentException ex) {
    System.out.println("unsupported = true");
}

try {
    toMap(null);
} catch (NullPointerException ex) {
    System.out.println("null = true");
}

Map<String, Object> immutable = toMap(new Invoice("INV-8", 90));
try {
    immutable.put("extra", 1);
} catch (UnsupportedOperationException ex) {
    System.out.println("readOnlyMap = true");
}
```

Đoạn này **không phải chương trình chạy độc lập**; đặt nguyên trong `main` của `TinyMapperDemo` và giữ import đã có. Khi ghép đúng, chương trình in thêm:

```text
unsupported = true
null = true
readOnlyMap = true
```

Các ví dụ thể hiện ba giới hạn rõ:

- Kiểu bất kỳ không được tự động introspect; mapper từ chối trước khi Reflection gọi accessor.
- Không truyền null như đối tượng nguồn.
- Người dùng không thể dùng `put` để sửa map kết quả.

Trong hệ thống thực tế, dùng unit test/assertion thay vì chỉ quan sát dòng in. Cần test cả object có property trả null, getter ném exception, class khác module, class chứa tham chiếu mutable và thay đổi phiên bản schema.

## 7. Mở rộng ánh xạ mà không phá hợp đồng

### a) Ánh xạ nhiều kiểu bằng registry được quản lý

Allowlist trong ví dụ phù hợp với hai lớp cho sẵn. Khi số kiểu tăng, có thể quản lý adapter đã đăng ký:

```java
interface ObjectMapper<T> {
    Map<String, Object> toMap(T source);
}
```

Đây là **khai báo interface minh họa**. Một registry theo `Class<?>` có thể trỏ mỗi kiểu sang một mapper tường minh; các kiểu không đăng ký bị từ chối. Khi thật sự cần Reflection để hỗ trợ record/JavaBean bất kỳ, hãy đặt quy tắc cho phép class/package, property, annotation và quyền riêng tư ngay tại ranh giới registry.

### b) Chỉ chọn thuộc tính cho phép công bố

Không phải getter public nào cũng nên xuất dữ liệu. Ví dụ `getPasswordHash()`, `getAccessToken()` hoặc `getInternalNotes()` có thể có trong class nhưng không phải nội dung trả cho client. Vì vậy serializer thật nên có allowlist property hoặc annotation opt-in, DTO chuyên trách, các phép biến đổi/redaction cụ thể và test bảo vệ dữ liệu.

**Reflection giúp tìm được member, không tự quyết định member có được công bố hay không.** Một log/map có dữ liệu nhạy cảm vẫn là rò rỉ dù toàn bộ lời gọi Reflection hợp lệ.

### c) Field trực tiếp và accessor có ý nghĩa khác nhau

Dùng `Field.get(...)` đọc field khai báo; dùng `Method.invoke(...)` trên getter thực thi logic của accessor. Getter có thể tính toán, kiểm tra quyền, lazy-load dữ liệu, hoặc ném exception. Trong nhiều domain, dùng accessor là cách hợp đồng API muốn công bố dữ liệu; nhưng với getter tốn chi phí, map toàn bộ có thể gây nhiều lời gọi DB (*N+1 query*) hay side effect.

Cần phân biệt “đọc value” với “thực thi getter”: mapper tự động gọi getter không an toàn cho mọi đối tượng không biết trước.

### d) Record mang dữ liệu, nhưng không bắt buộc là schema JSON

`RecordComponent.getAccessor()` cung cấp tên kiểu Java. Nếu tên JSON khác tên Java, hoặc cần phiên bản hóa, nullable, nested conversion, ngày/giờ, enum encoding, polymorphism, default values và schema evolution, bạn cần quy tắc mapping bổ sung.

Một record như `record User(String firstName, List<String> roles)` không tự động biến thành JSON đúng schema chỉ bằng cách bỏ các value vào map. Cần bộ chuyển đổi có hợp đồng về nested types và null, hoặc thư viện serialization được cấu hình rõ.

### e) Ánh xạ chiều ngược

Tạo record từ map cần tìm **canonical constructor** với kiểu và thứ tự component chính xác, lấy giá trị theo tên, kiểm tra null với primitive, ép/chuyển đổi kiểu, xử lý unknown/missing keys và gọi constructor. Với JavaBean, cần biết constructor/setter/builder nào được phép. Đây là một nghiệp vụ riêng, dễ gây lỗi dữ liệu hơn chiều đọc.

Không tự viết chiều ngược bằng cách lấy tất cả private field rồi `setAccessible(true)` để set tùy ý: có thể phá invariants, gặp field final/module restrictions và bỏ qua validation. Nếu cần deserialize trong hệ thống thật, sử dụng DTO/constructor rõ ràng hoặc thư viện có quy tắc schema.

## 8. Lỗi Reflection thường gặp

| Lỗi | Nơi có thể gặp | Nguyên nhân/cách xử lý |
| --- | --- | --- |
| `IllegalAccessException` | `Method.invoke` | Accessor hoặc lớp chứa không truy cập được; xem visibility/module và vị trí code gọi |
| `InvocationTargetException` | `Method.invoke` | Getter đã được gọi nhưng tự ném lỗi; xem `getCause()` |
| `IntrospectionException` | `Introspector.getBeanInfo` | Không introspect được JavaBeans metadata theo yêu cầu |
| `IllegalArgumentException` | Kiểm tra allowlist hoặc gọi method sai receiver | Bản ví dụ cố ý từ chối class chưa đăng ký; phân biệt với lỗi kiểu đối số Reflection |
| `NullPointerException` | `Objects.requireNonNull(source)` | Thiếu đối tượng nguồn |
| `UnsupportedOperationException` | Caller `put` vào map trả về | Map kết quả bị khóa sửa cấu trúc |
| Trùng/thiếu property | Mapper thiết kế sai hoặc accessor không có | Dùng đúng `RecordComponent`/`PropertyDescriptor` và xác định chính sách lọc |
| Value thay đổi ngoài ý muốn | Getter có side effect hoặc trả về object mutable | Không xem giá trị trả về là snapshot bất biến sâu |

Đừng chỉ catch `Exception` rồi bỏ qua property lỗi. Khi mapper tự động lược bỏ một trường, người dùng có thể nhận một bản đồ **có vẻ thành công** nhưng thiếu dữ liệu quan trọng. Nếu sản phẩm yêu cầu best-effort mapping, phải định nghĩa rõ kiểu kết quả chứa cả lỗi theo từng trường; bài này chọn **fail-fast** để không che giấu lỗi.

## 9. Một số giới hạn hiệu năng và vòng đời

Lấy `getRecordComponents()` hoặc gọi `Introspector.getBeanInfo(...)` thường không nên lặp lại một cách vô ích trong vòng lặp xử lý lượng lớn object cùng loại. Có thể cache danh sách metadata/accessor theo `Class<?>` hoặc giữ một mapping plan theo schema.

Tuy nhiên cache phải quan tâm đến classloader: static `Map<Class<?>, ...>` với strong reference có thể giữ lớp từ plugin/redeploy trong bộ nhớ. Với metadata theo class, `ClassValue<T>` là một lựa chọn thích hợp; cache vòng đời component cũng có thể đơn giản hơn. `Introspector` còn có cơ chế cache nội bộ; khi quản lý lớp động có thể cần xem API `Introspector.flushFromCaches(type)` tại thời điểm phù hợp.

Trong phạm vi bài thực hành, không thêm cache để giữ code dễ đọc. Chỉ bổ sung sau khi đo được metadata discovery là điểm nóng. Với ứng dụng production, so sánh mapper Reflection với mapper tường minh, kiểm thử hiệu năng sau JIT warmup và đo cả chi phí getter.

## 10. Bài tập mở rộng

1. Tạo `record Point(int x, int y)`. Cho phép thêm record đó vào mapper, in kết quả và giải thích thứ tự các key khi dùng `TreeMap`.
2. Thêm JavaBean có `getTitle()`, `isPublished()` và method `calculateChecksum()`. Vì sao method thứ ba không trở thành property JavaBeans hợp lệ theo quy ước?
3. Thêm getter trả null. Chứng minh kết quả vẫn có key với value null và lý giải tại sao đổi sang `Map.copyOf(...)` sẽ không phù hợp.
4. Thêm getter cố ý ném `IllegalStateException("offline")`. Xác nhận mapper không bỏ qua lỗi, giữ được cause gốc từ `InvocationTargetException`.
5. Thử gọi `toMap(new Object())`. Giải thích lý do allowlist quan trọng khi dữ liệu nguồn không được tin cậy.
6. Thay `TreeMap` bằng `LinkedHashMap`. Với record, kiểm tra thứ tự khai báo của component ảnh hưởng thứ tự duyệt map thế nào.
7. Bổ sung danh sách tên property được cho phép vào mapper; không xuất các property như `passwordHash` hoặc `secretKey` dù getter public.
8. Thảo luận vì sao ánh xạ ngược `Map → record` cần thêm kiểm tra constructor, type conversion, missing key và validation. Viết đề xuất API rõ ràng trước khi coding.

### Checklist nghiệm thu

- Chương trình biên dịch/chạy trên Java 17+.
- Record dùng `getRecordComponents()` và `getAccessor()`, JavaBean dùng `Introspector` và `getReadMethod()`.
- Không dùng `setAccessible(true)` để bỏ qua quyền Java.
- Không lộ property `class` do `Object.getClass()`.
- Kết quả của hai kiểu khớp output đã công bố.
- Input null và loại chưa đăng ký được xử lý tường minh.
- Lỗi từ accessor được giữ nguyên cause để chẩn đoán.
- Các giới hạn về nested objects, null, bảo mật dữ liệu và quyền truy cập được mô tả rõ.

**Kết quả cần đạt:** tự viết được bộ ánh xạ một chiều quy mô nhỏ bằng accessor/record component; đọc đúng metadata của hai mô hình Java, gọi accessor có kiểm soát, xử lý lỗi Reflection và biết khi nào nên thay mini mapper bằng API tường minh hoặc công cụ serialization chuyên dụng.
