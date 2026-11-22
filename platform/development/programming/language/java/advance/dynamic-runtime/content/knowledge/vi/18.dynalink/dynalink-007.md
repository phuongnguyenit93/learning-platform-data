# 18.7. Thao tác trên đối tượng Java, chuyển đổi kiểu và lỗi `NoSuchDynamicMethodException` trong Dynalink

Khi một runtime ngôn ngữ động chạy trên JVM gặp biểu thức như `object.color`, `object.join(value)`, `list[index]` hoặc `new JavaClass()`, kiểu Java thực của đối tượng có thể chỉ biết **lúc chương trình chạy**. `jdk.dynalink` (Java 9+) cung cấp hạ tầng liên kết các phép toán cấp cao đó với `MethodHandle` tương ứng. **`BeansLinker`** là linker có sẵn để thao tác với các đối tượng Java thông thường: JavaBean property, public field, method, record accessor, `List`, `Map`, array, static member và constructor.

Cũng cần hiểu giới hạn: Dynalink **không biến mọi giá trị thành mọi kiểu**, không truy cập tùy tiện mọi member private, và không tự bảo đảm mọi tên phép toán đều tồn tại. Khi không linker nào có thể giải một operation phù hợp, hệ thống có thể ném **`jdk.dynalink.NoSuchDynamicMethodException` ở thời điểm gọi**, khác với lỗi chọn overload, lỗi chuyển đổi kiểu và lỗi descriptor của `MethodHandle.invokeExact`.

Bài học thuộc nhóm **18. Dynalink**, tập trung vào ba câu hỏi:

1. Dynalink diễn tả, liên kết và thực thi các thao tác **trên đối tượng Java** thế nào?
2. `BeansLinker` cùng các dịch vụ chuyển đổi kiểu chọn method overload và thích ứng đối số/giá trị trả về ra sao?
3. Khi nào thực sự phát sinh `NoSuchDynamicMethodException`, và phân biệt nó với `NoSuchMethodException`, `ClassCastException`, `WrongMethodTypeException` như thế nào?

Có chương trình Java 17+ **độc lập**, không dùng thư viện ngoài, minh họa toàn bộ những nhóm tình huống trên, kèm lệnh biên dịch và 20 dòng `stdout` đã chạy kiểm chứng.

## 1. Dynalink là thư viện liên kết động, không phải bản thân một ngôn ngữ

Module chuẩn của **JDK** là `jdk.dynalink`. Các kiểu cốt lõi gồm:

- `DynamicLinkerFactory`: cấu hình/thành lập một `DynamicLinker`.
- `DynamicLinker`: phối hợp các linker để tìm cách thực hiện operation tại một call site.
- `Operation`, `StandardOperation`, `StandardNamespace`, `NamedOperation`: diễn tả phép toán như đọc property `color`, đọc một phần tử hoặc gọi một dynamic method.
- `CallSiteDescriptor`: mô tả `Lookup`, operation và `MethodType` của điểm gọi.
- `SimpleRelinkableCallSite`: một implementation của `RelinkableCallSite` có thể đổi target khi runtime gặp receiver khác.
- `BeansLinker`: linker fallback cho các đối tượng Java; nó ánh xạ operations sang getter/setter/field/method/element/constructor.
- `LinkerServices`, `GuardingTypeConverterFactory` và các API liên quan: hỗ trợ thích ứng kiểu và tích hợp bộ chuyển đổi của ngôn ngữ khác.

`jdk.dynalink` dựa trên các primitives trong `java.lang.invoke` nhưng ở **mức trừu tượng cao hơn**. `MethodHandle` chỉ biết gọi một đích có kiểu; Dynalink còn hiểu câu hỏi “hãy lấy property `color` của object hiện tại” và có thể chọn getter khác khi object thay đổi kiểu tại runtime.

```text
Ứng dụng / runtime ngôn ngữ
          |
          | Operation: GET:PROPERTY:color
          | MethodType: (Object)Object
          v
CallSiteDescriptor + RelinkableCallSite
          |
          v
      DynamicLinker
          |
    linkers ưu tiên (nếu có)
          |
    linkers được discover (nếu có)
          |
    BeansLinker fallback
          |
          v
guard + target MethodHandle
          |
          v
thực thi getter/field trên Java receiver
          |
          +-- Nếu receiver class khác:
                  guard không khớp -> relink
```

Nếu không có linker nào nhận operation và thực hiện được liên kết tại điểm gọi, Dynalink không thể tự “đoán” một method thay thế. Khi caller thực thi điểm gọi đó, `NoSuchDynamicMethodException` là một khả năng theo contract.

### 1.1. Không cần tự tạo bytecode `invokedynamic` để thử API

Dynalink thường được dùng trong bootstrap của instruction `invokedynamic`, nhưng bạn cũng có thể tạo `RelinkableCallSite` trong Java code thường rồi dùng `dynamicInvoker()` để chạy. Ví dụ ở mục 7 chọn hướng này để dễ kiểm thử, không cần ASM hoặc công cụ sinh bytecode.

**Không nhầm:** `DynamicLinker.link(...)` thiết lập call site có thể relink, nhưng trường hợp không có operation hợp lệ có thể **không báo lỗi ngay lúc xây descriptor hoặc gọi `link`**. Lỗi linkage thường xuất hiện khi **thực sự invoke** và DynamicLinker tìm linker cho các giá trị runtime.

## 2. Biểu diễn thao tác: `StandardOperation` và `StandardNamespace`

Dynalink không nhận chuỗi ngôn ngữ bất kỳ như `"obj.color"` rồi tự phân tích. Người tích hợp phải tạo đúng **Operation**.

Các operation chuẩn được Javadoc Java 17 định nghĩa:

| Operation | Ý nghĩa | Chữ ký logic |
| --- | --- | --- |
| `GET` + namespace | Lấy property/element/method | `(receiver, name) → value`, hoặc `(receiver) → value` khi đã `named(...)` |
| `SET` + namespace | Ghi property/element | `(receiver, name, value) → void`, hoặc `(receiver, value) → void` khi `named(...)` |
| `REMOVE` + namespace | Xóa element | `(receiver, name) → void`, hoặc `(receiver) → void` khi đã `named(...)` |
| `CALL` | Gọi một callable object | `(callable, receiver, arguments...) → result` |
| `NEW` | Tạo đối tượng từ constructor object | `(constructor, arguments...) → result` |

**`GET`, `SET` và `REMOVE` cần namespace**. Với Java, những namespace phổ biến:

| Namespace | Diễn giải | Đối tượng Java được `BeansLinker` hỗ trợ |
| --- | --- | --- |
| `StandardNamespace.PROPERTY` | Thuộc tính theo tên | Getter/setter JavaBean, public field, accessor record, property tổng hợp như `length` |
| `StandardNamespace.METHOD` | Method theo tên | Lấy **dynamic method object**, sau đó `CALL` để thực thi |
| `StandardNamespace.ELEMENT` | Phần tử theo key/index | Native array, `List`, `Map` |

Một getter property được đặt tên `color` có thể diễn tả:

```java
Operation getColor = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("color");
```

Sau `named("color")`, không còn cần truyền string `"color"` như tham số runtime. Do đó một CallSiteDescriptor kiểu `(Object)Object` đủ cho `GET:PROPERTY:color`. Ngược lại, getter element **không cố định key** có thể dùng kiểu `(Object,Object)Object` để truyền receiver và key/index trong từng lần gọi.

Phân biệt thật rõ:

```java
StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY).named("color");
StandardOperation.GET
        .withNamespace(StandardNamespace.METHOD).named("join");
StandardOperation.GET
        .withNamespace(StandardNamespace.ELEMENT);
```

Ba biểu thức tạo **ba operation khác nhau**, dù đều có tiền tố `GET`. Đây là code minh họa, không phải một file Java chạy độc lập.

### 2.1. `CALL` không phải `GET:METHOD`

Với Java object `bean` có method `join(String)`:

1. `GET:METHOD:join` trả một **dynamic method object** được `BeansLinker` nhận diện. Nó chưa gọi `join`.
2. `CALL` nhận **callable object** đó, **receiver** và các đối số, rồi chọn overload thích hợp.

Tại sao truyền receiver hai lần trong chuỗi thao tác? Vì lần đầu cần receiver để **tìm** dynamic method; lần gọi `CALL` cần receiver để **thực thi** method trên object. Với API chuẩn, chữ ký của `CALL` có dạng `(callable, receiver, args...)`. Đừng tưởng đối tượng method lấy ra từ `GET:METHOD` luôn là Java `Method` hay một `MethodHandle` đã bind receiver sẵn.

Ví dụ sau thực sự được kiểm chứng:

```java
Object callable = getJoin.invokeExact((Object) bean);
Object result = call.invokeExact(
        callable, (Object) bean, (Object) "abc");
```

Đây là snippet trích từ chương trình mục 7; `getJoin` và `call` đã được link với descriptor phù hợp trong chương trình đó.

## 3. `BeansLinker`: liên kết các member và collection Java

`DynamicLinkerFactory` mặc định chuẩn bị một `BeansLinker` làm fallback cuối, nếu bạn không chủ động thay tập fallback linkers. Điều này cho phép xử lý object Java ngay cả khi bạn chưa xây riêng linker cho ngôn ngữ khác.

### 3.1. JavaBean getter/setter và public field

Với class:

```java
public static class ColorBean {
    private String color = "red";

    public String getColor() { return color; }
    public void setColor(String value) { color = value; }
}
```

`GET:PROPERTY:color` sẽ ánh xạ tới getter `getColor()`, `SET:PROPERTY:color` tới setter `setColor(...)`. Field `color` ở đây là **private**; Dynalink không cần tự truy cập private field vì dùng **public accessor**.

`BeansLinker` còn hỗ trợ **public field** như property. Nếu một tên đồng thời có public field và getter/setter, các accessor JavaBean được ưu tiên theo quy tắc linker. Không hứa rằng dùng Dynalink có thể đọc/ghi mọi field private như khi bật `setAccessible(true)`; kiểm tra quyền visibility và module vẫn được áp dụng.

Một property thường được suy từ method `getXxx()`, `isXxx()` hoặc `setXxx(...)` (theo contract của `BeansLinker`), không bắt buộc tồn tại field `xxx` trong object.

### 3.2. Java record

Từ Java 16, record cung cấp component accessors với tên chính là component, ví dụ:

```java
public record Box(String title) {}
```

`BeansLinker` của Java 17 cho phép `GET:PROPERTY:title` đọc giá trị bằng accessor `Box.title()` dù đó không phải getter mang tên `getTitle()`.

Trong chương trình độc lập, `GET:PROPERTY:title` trên `new Box("record")` trả `"record"`. Không tổng quát rằng mọi method public có một đối số nào đó đều tự biến thành property hợp lệ: API đặc tả rõ các trường hợp được `BeansLinker` hỗ trợ.

### 3.3. Array, `List`, `Map`

`GET/SET` trong namespace `ELEMENT` có thể truy cập phần tử:

```java
// Link GET:ELEMENT với MethodType (Object,Object)Object
Object second = getElement.invokeExact(
        (Object) list, (Object) Integer.valueOf(1));

// Link SET:ELEMENT với MethodType (Object,Object,Object)void
setElement.invokeExact(
        (Object) map, (Object) "key", (Object) 42);
```

`List` thường dùng index, `Map` dùng key, array dùng index. Với `Map`, `REMOVE:ELEMENT` có thể xóa entry. Với `List`, remove có thể làm thay đổi size/index; với array kích thước cố định, không suy có thể remove element.

`BeansLinker` cũng cung cấp property tổng hợp `length` cho array, `Collection` và `Map`:

```java
Operation length = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("length");
```

Trên array `{"x","y"}`, operation này trả độ dài `2`. Nếu bạn muốn đọc `Map.size()` theo method namespace, đó là lựa chọn khác với dùng virtual property `length`; đừng nhầm method/property/element có cùng mô hình tham số.

### 3.4. Static member và constructor cần `StaticClass`

Một `Class<?>` thông thường **không** được `BeansLinker` coi là namespace static member một cách trực tiếp. Ví dụ `ColorBean.class` là đối tượng Java `Class` với các method như `getName()`, `getSuperclass()`. Muốn `GET:METHOD:banner` trên static method hoặc `NEW` tạo instance, dùng:

```java
StaticClass staticFacet = StaticClass.forClass(ColorBean.class);
```

`StaticClass` là wrapper mà `BeansLinker` nhận diện và dùng để chọn static methods, static properties và constructors của class được đại diện. `StandardOperation.NEW` với một `StaticClass` phù hợp có thể chọn constructor Java hợp lệ, kể cả khi overloaded.

**Không được** suy rằng `StandardOperation.NEW` trên **bất kỳ object Java** nào cũng tạo object mới. Với `new ColorBean()` làm receiver cho `NEW`, nếu không linker nào hỗ trợ, Dynalink có thể ném `NoSuchDynamicMethodException`.

## 4. Cách tạo một dynamic call site

Một chương trình Java có thể dựng `DynamicLinker`:

```java
DynamicLinker linker = new DynamicLinkerFactory().createLinker();
```

Sau đó tạo `CallSiteDescriptor` với `MethodHandles.Lookup`, `Operation` và `MethodType`:

```java
CallSiteDescriptor descriptor = new CallSiteDescriptor(
        MethodHandles.lookup(),
        StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("color"),
        MethodType.methodType(Object.class, Object.class));
```

`SimpleRelinkableCallSite` là dạng call site có thể cập nhật target. Sau khi link:

```java
MethodHandle getter = linker.link(
        new SimpleRelinkableCallSite(descriptor)).dynamicInvoker();
```

`getter` có kiểu `(Object)Object` như descriptor, không phải tự nhận bất kỳ chữ ký Java nào. Khi gọi `getter.invokeExact((Object)bean)` với return expression gán vào biến `Object`, descriptor của caller khớp. Nếu gọi `getter.invokeExact(...)` mà bỏ kết quả như một **statement**, compiler tạo call-site descriptor có return `void`; điều này có thể gây `WrongMethodTypeException` vì handle thực trả `Object`. Đó là lỗi của `invokeExact`, **không phải** lỗi thiếu Java member.

**Quan hệ với relinking:** Nếu cùng getter được gọi với hai receiver class khác nhau, target đã link cho class đầu có guard. Khi guard không còn phù hợp, `DynamicLinker` có thể relink cho class thứ hai. `SimpleRelinkableCallSite` thường lưu liên kết cho kiểu gặp gần nhất (*monomorphic*); `ChainedCallSite` có thể giữ nhiều guard-target pairs (*polymorphic*), phù hợp bài toán receiver thường xuyên đổi loại. Đây là lựa chọn chính sách cache linkage, không phải thay đổi semantics getter mà bạn yêu cầu.

### 4.1. Sơ đồ lời gọi và lỗi

```text
1. linker.link(relinkableCallSite)
             |
             +--> tạo target ban đầu để liên kết khi cần
2. caller gọi dynamicInvoker.invokeExact(receiver, args...)
             |
             v
3. Dynalink có linkage phù hợp với receiver hiện tại?
             |
       +-----+-----+
       |           |
      Có          Không
       |           |
       |       hỏi các GuardingDynamicLinker
       |           |
       |       +---+----------------+
       |       |                    |
       |      Có                   Không
       |       |                    |
       |     guard + target         NoSuchDynamicMethodException
       |       |
       +-------+
               |
               v
4. Adapt arguments/return theo MethodType và conversions
               |
               +--> chuyển đổi/overload có thể lỗi riêng
               |
               v
5. Gọi method/field/constructor thực của Java
               |
               +--> exception do method Java tự ném có thể đi ra
```

Sơ đồ mô tả các giai đoạn **khái niệm**; JIT và linker có thể tối ưu, kết hợp hoặc hoãn các bước. Nó không phải stack trace cố định hoặc promise rằng mọi exception phát sinh ở đúng một dòng như sơ đồ.

## 5. Chuyển đổi kiểu: có thích ứng, nhưng không phải “ép bừa”

Dynalink có `LinkerServices` để các linkers điều chỉnh `MethodHandle` tới chữ ký tại dynamic call site. Với linker cho đối tượng Java mặc định, các chuyển đổi theo Java method-handle semantics là nền tảng; các runtime ngôn ngữ khác có thể cung cấp `GuardingTypeConverterFactory` và `MethodTypeConversionStrategy` để định nghĩa coercion đặc thù.

Đối với ứng dụng, **phân biệt ba lớp kiểu**:

1. **Kiểu của receiver/đối số thực:** `String`, `Integer`, `Short`, `ColorBean`...
2. **`MethodType` của dynamic call site:** ví dụ `(Object,Object,Object)Object` cho `CALL`, hoặc `(Object,short)void` cho setter.
3. **Kiểu Java member đích:** `join(String)`, `join(int)`, `setCount(int)`.

Điều hợp lệ là Dynalink tìm/adapt một cách gọi tương thích theo contract, không phải một lần convert “đúng với mọi engine” bất kể dữ liệu.

### 5.1. Widening primitive: `short` → `int`

Một JavaBean có setter:

```java
public void setCount(int value) { count = value; }
```

Ta có thể link `SET:PROPERTY:count` với descriptor `(Object,short)void` rồi gọi:

```java
setCount.invokeExact((Object) bean, (short) 7);
```

`BeansLinker` chọn setter nhận `int`; `short` được **widening** thành `int`. Trong ví dụ thật, `bean.getCount()` trả `7`. Đây là một chuyển đổi kiểu có chủ đích và an toàn theo hệ thống method-handle adaptation.

### 5.2. Boxing/unboxing và runtime overload selection

Giả sử có hai overload:

```java
public String join(String text) { return "text:" + text; }
public String join(int value)   { return "number:" + value; }
```

Một call site `CALL` được khai báo `(Object,Object,Object)Object`, trong đó argument cuối được truyền kiểu `Object` nhưng **runtime value** có thể là `String` hoặc `Integer`. Dynalink dùng thông tin động để chọn phương thức:

```java
Object a = call.invokeExact(
        callable, (Object) bean, (Object) "abc");
Object b = call.invokeExact(
        callable, (Object) bean, (Object) Integer.valueOf(3));
```

Trong chương trình mục 7, `a == "text:abc"` và `b == "number:3"`. Với `Integer`, linker có thể unbox để gọi `join(int)`. Điều này không có nghĩa mọi overload đều tự quyết định duy nhất: khi nhiều overload áp dụng ngang nhau, lựa chọn có thể mơ hồ, tùy signatures và các conversion rules do runtime cung cấp.

### 5.3. Không có mặc định “`String` → `int` bằng parse số”

`"7"` là `String`; `7` là primitive `int`; `Integer.valueOf(7)` là wrapper `Integer`. Dynalink/BeansLinker **không cam kết** tự gọi `Integer.parseInt("7")` khi setter cần `int`.

Trong chương trình kiểm thử, dùng `SET:PROPERTY:count` với tham số dynamic type `Object` rồi truyền `"7"` gây `ClassCastException` khi kế hoạch chuyển đổi không thể thực thi. Nếu ngôn ngữ nhúng muốn tự parse string thành number, phải cung cấp **conversion policy riêng** qua linker/type converter hoặc tự convert trước khi gọi.

Dù JVM cho phép một số primitive conversions, đừng coi mọi giá trị object có vẻ “in được thành số” sẽ được đổi hợp lệ. Chuyển đổi sai kiểu có thể thất bại **lúc adapt handle**, lúc chọn overload hoặc lúc invoke.

### 5.4. `LinkerServices` và custom conversion

`LinkerServices.asType(MethodHandle, MethodType)` kết hợp quy tắc `MethodHandle.asType` với các converter do `GuardingTypeConverterFactory` cung cấp. `canConvert(from, to)` hỏi liệu một conversion **có thể tồn tại**, không bảo đảm mọi runtime value đều thành công. `compareConversion` cho linker thêm thông tin để phân giải overload khi nhiều target có thể nhận đối số.

Ví dụ một runtime ngôn ngữ có type `BigNumber` riêng có thể cho phép conversion đến `int` theo chính sách overflow/clamping/exception cụ thể. **Đó là chính sách của runtime được tích hợp**, không phải hành vi mặc định của mọi `BeansLinker` hoặc JavaScript engine.

Tương tự, `setAutoConversionStrategy(...)` trên `DynamicLinkerFactory` cho phép tùy biến conversion behavior ở thời điểm phối hợp linking. Nếu thay một strategy, cần test đầy đủ các dạng primitive widening/narrowing, boxing/unboxing, null, overload và return type; không chỉ test một case thành công.

### 5.5. Chữ ký `invokeExact` và chữ ký operation

Ngay cả khi linker đã tạo đúng target, caller vẫn phải gọi `invokeExact` với descriptor **khớp chính xác** `MethodHandle.type()`. Đây không phải quy tắc overload JavaBean, mà là quy tắc riêng của `java.lang.invoke.MethodHandle`.

Ví dụ `getColor` có kiểu `(Object)Object`:

```java
Object ok = getColor.invokeExact((Object) bean); // Đúng.
getColor.invokeExact((Object) bean);             // Sai return descriptor: void.
```

Dòng thứ hai được cố tình đặt trong khối `try/catch` ở ví dụ độc lập và ném `WrongMethodTypeException`. Nó không được sửa bằng cách thêm một `GuardingDynamicLinker` mới vì việc thất bại đã xảy ra **ở chữ ký của lời gọi handle**. Nếu muốn adaptation theo call-site context, nghiên cứu `invoke` hoặc `asType` với semantics riêng và kiểm soát chi phí/loại chuyển đổi.

## 6. `NoSuchDynamicMethodException` nghĩa là gì?

**Chữ ký/ý nghĩa:** `jdk.dynalink.NoSuchDynamicMethodException` là một `RuntimeException`, tài liệu mô tả: được ném **tại invocation** nếu không `GuardingDynamicLinker` khả dụng nào có thể link call site đó.

Điều này rộng hơn “không tìm thấy method Java tên X”: operation có thể là `GET:PROPERTY`, `SET:ELEMENT`, `NEW`... và vấn đề là **không có đường liên kết phù hợp** cho receiver, operation và signature hiện tại.

Những ví dụ đã kiểm chứng với default `BeansLinker`:

- `GET:METHOD:absent` trên `ColorBean` không có method đó → `NoSuchDynamicMethodException`.
- `GET:PROPERTY:absent` trên `ColorBean` không có readable property đó → `NoSuchDynamicMethodException`.
- `NEW` trên **instance thường** của `ColorBean` thay vì `StaticClass` → `NoSuchDynamicMethodException`.

Ngoại lệ **không nhất thiết xảy ra ngay khi gọi `link(...)`**; việc link thực tế phụ thuộc giá trị runtime ở lần invocation. Cũng không nhất thiết có lỗi nếu một custom linker hoặc một `MissingMemberHandlerFactory` đã được cài để cung cấp fallback cho member thiếu.

### 6.1. So sánh với ba lỗi rất dễ nhầm

| Lỗi | Lý do thường gặp | Ví dụ kiểm chứng |
| --- | --- | --- |
| **`NoSuchDynamicMethodException`** | Không linker nào cung cấp linkage cho operation tại call site | `GET:METHOD:absent`; `NEW` trên Java instance thường |
| **`NoSuchMethodException`** | Dynamic method đã có nhưng không thể lựa chọn overload tương ứng với danh sách đối số runtime | `CALL` với `join(String)`/`join(int)` nhưng truyền `new Object()` |
| **`ClassCastException`** | Có đường gọi/conversion nhưng giá trị runtime không phù hợp với phép chuyển đổi được đặt vào handle | `SET:PROPERTY:count` nhận `"7"` cho setter `int` trong ví dụ |
| **`WrongMethodTypeException`** | Call-site descriptor của `invokeExact` khác `MethodHandle.type()` | Gọi getter trả `Object` như statement trả `void` |

**Điểm quan trọng:** `NoSuchMethodException` là checked exception trong Java reflection API, nhưng ở ví dụ Dynalink nó có thể được ném **trong quá trình invocation/overload resolution của dynamic method object** và truyền ra caller `throws Throwable`. Không suy ra rằng tất cả lỗi “không có method” trong Dynalink luôn là `NoSuchDynamicMethodException` hoặc ngược lại. Khi lựa chọn overload, tương tác giữa các converters, varargs và types có thể quyết định loại lỗi cụ thể.

Tương tự, `ClassCastException` không phải là bằng chứng mọi conversion đều được xử lý sau khi linker đã tìm ra method; đó là **kết quả quan sát được** ở ví dụ với giá trị `String`, target setter `int` và descriptor đã dùng.

### 6.2. Lỗi access và exception do method đích

`BeansLinker` làm việc với những member mà policy của Java/`Lookup` cho phép. Nó không biến member private thành public. Một method có thể không link được vì access constraints hoặc module restrictions, dù tên tồn tại trong reflection. Ngược lại, một target Java **đã link hợp lệ** có thể tự ném `IllegalArgumentException`, `IOException` hoặc exception nghiệp vụ khác — đây là lỗi **trong method đích**, không phải lỗi do Dynalink không tìm được operation.

Khi debug, nên tách bốn bước: **operation descriptor → receiver class/lookup → overload/conversion → execution target**, rồi đọc stack trace và cause chain thay vì đoán từ mỗi tên exception.

### 6.3. `MissingMemberHandlerFactory` thay đổi semantics của member thiếu

`BeansLinker` có constructor nhận `MissingMemberHandlerFactory`. Nó cho phép runtime ngôn ngữ định nghĩa fallback khi một property/method không tồn tại. Một ngôn ngữ muốn “missing property trả undefined” có thể đưa policy đó vào linker; khi đó thiếu property có thể **không** sinh `NoSuchDynamicMethodException` như default configuration.

Không viết catch `NoSuchDynamicMethodException` rồi mặc nhiên trả `null` cho **mọi** operation: đó sẽ che lỗi cấu hình, lỗi constructor, lỗi property name và lỗi API contract. Nếu ngôn ngữ cần semantics “missing → undefined”, hãy thiết kế rõ ở policy/linker và phân biệt nó với lỗi runtime phải được báo.

## 7. Chương trình Java 17+ chạy được: property, element, method, constructor, conversion, exceptions

Chương trình sau dùng `DynamicLinkerFactory` và `SimpleRelinkableCallSite`; không cần tạo bytecode `invokedynamic`. Một helper `link(...)` tạo `CallSiteDescriptor` cho từng operation và trả `dynamicInvoker()`. Mọi ví dụ đều dùng **`BeansLinker` mặc định**, không có custom converter hoặc missing-member handler.

Lưu toàn bộ mã dưới tên **`DynalinkJavaObjectsDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.NoSuchDynamicMethodException;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.beans.BeansLinker;
import jdk.dynalink.beans.StaticClass;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkJavaObjectsDemo {
    public static class ColorBean {
        private String color = "red";
        private int count;

        public String getColor() { return color; }
        public void setColor(String value) { color = value; }
        public int getCount() { return count; }
        public void setCount(int value) { count = value; }
        public String join(String text) { return "text:" + text; }
        public String join(int value) { return "number:" + value; }
        public static String banner() { return "STATIC"; }
    }

    public record Box(String title) {}

    private static final DynamicLinker LINKER =
            new DynamicLinkerFactory().createLinker();

    private static MethodHandle link(Operation operation, MethodType type) {
        CallSiteDescriptor descriptor = new CallSiteDescriptor(
                MethodHandles.lookup(), operation, type);
        return LINKER.link(new SimpleRelinkableCallSite(descriptor))
                .dynamicInvoker();
    }

    public static void main(String[] args) throws Throwable {
        ColorBean bean = new ColorBean();

        MethodHandle getColor = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.PROPERTY).named("color"),
                MethodType.methodType(Object.class, Object.class));
        MethodHandle setColor = link(
                StandardOperation.SET.withNamespace(
                        StandardNamespace.PROPERTY).named("color"),
                MethodType.methodType(void.class, Object.class, Object.class));

        Object oldColor = getColor.invokeExact((Object) bean);
        setColor.invokeExact((Object) bean, (Object) "blue");
        Object newColor = getColor.invokeExact((Object) bean);
        System.out.println("property=" + oldColor + "->" + newColor);

        MethodHandle setCount = link(
                StandardOperation.SET.withNamespace(
                        StandardNamespace.PROPERTY).named("count"),
                MethodType.methodType(void.class, Object.class, short.class));
        setCount.invokeExact((Object) bean, (short) 7);
        System.out.println("shortToInt=" + bean.getCount());

        MethodHandle getJoin = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.METHOD).named("join"),
                MethodType.methodType(Object.class, Object.class));
        Object callable = getJoin.invokeExact((Object) bean);
        System.out.println("isDynamicMethod=" + BeansLinker.isDynamicMethod(callable));

        MethodHandle call = link(
                StandardOperation.CALL,
                MethodType.methodType(
                        Object.class, Object.class, Object.class, Object.class));
        Object stringResult = call.invokeExact(
                callable, (Object) bean, (Object) "abc");
        Object integerResult = call.invokeExact(
                callable, (Object) bean, (Object) Integer.valueOf(3));
        System.out.println("overload.string=" + stringResult);
        System.out.println("overload.integer=" + integerResult);

        MethodHandle exactJoin = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.METHOD).named("join(String)"),
                MethodType.methodType(Object.class, Object.class));
        Object selected = exactJoin.invokeExact((Object) bean);
        Object selectedResult = call.invokeExact(
                selected, (Object) bean, (Object) "xyz");
        System.out.println("explicitSignature=" + selectedResult);

        MethodHandle getElement = link(
                StandardOperation.GET.withNamespace(StandardNamespace.ELEMENT),
                MethodType.methodType(
                        Object.class, Object.class, Object.class));
        MethodHandle setElement = link(
                StandardOperation.SET.withNamespace(StandardNamespace.ELEMENT),
                MethodType.methodType(
                        void.class, Object.class, Object.class, Object.class));
        MethodHandle removeElement = link(
                StandardOperation.REMOVE.withNamespace(StandardNamespace.ELEMENT),
                MethodType.methodType(void.class, Object.class, Object.class));

        List<String> list = Arrays.asList("one", "two");
        Object second = getElement.invokeExact(
                (Object) list, (Object) Integer.valueOf(1));
        System.out.println("list[1]=" + second);

        Map<String,Object> map = new HashMap<>();
        setElement.invokeExact((Object) map, (Object) "key", (Object) 42);
        Object mapValue = getElement.invokeExact((Object) map, (Object) "key");
        removeElement.invokeExact((Object) map, (Object) "key");
        System.out.println("map.value=" + mapValue);
        System.out.println("map.removed=" + !map.containsKey("key"));

        String[] array = {"x", "y"};
        Object arrayValue = getElement.invokeExact(
                (Object) array, (Object) Integer.valueOf(1));
        MethodHandle getLength = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.PROPERTY).named("length"),
                MethodType.methodType(Object.class, Object.class));
        Object length = getLength.invokeExact((Object) array);
        System.out.println("array.value=" + arrayValue);
        System.out.println("array.length=" + length);

        MethodHandle getTitle = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.PROPERTY).named("title"),
                MethodType.methodType(Object.class, Object.class));
        Object title = getTitle.invokeExact((Object) new Box("record"));
        System.out.println("record.title=" + title);

        StaticClass staticFacet = StaticClass.forClass(ColorBean.class);
        MethodHandle getBanner = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.METHOD).named("banner"),
                MethodType.methodType(Object.class, Object.class));
        Object banner = getBanner.invokeExact((Object) staticFacet);
        MethodHandle callNoArgs = link(
                StandardOperation.CALL,
                MethodType.methodType(
                        Object.class, Object.class, Object.class));
        Object bannerResult = callNoArgs.invokeExact(
                banner, (Object) staticFacet);
        System.out.println("static.banner=" + bannerResult);

        MethodHandle construct = link(
                StandardOperation.NEW,
                MethodType.methodType(Object.class, Object.class));
        Object created = construct.invokeExact((Object) staticFacet);
        System.out.println("new.class=" + created.getClass().getSimpleName());

        MethodHandle missingMethod = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.METHOD).named("absent"),
                MethodType.methodType(Object.class, Object.class));
        try {
            Object ignored = missingMethod.invokeExact((Object) bean);
            System.out.println("missing.method=unexpected:" + ignored);
        } catch (NoSuchDynamicMethodException e) {
            System.out.println("missing.method=" + e.getClass().getSimpleName());
        }

        MethodHandle missingProperty = link(
                StandardOperation.GET.withNamespace(
                        StandardNamespace.PROPERTY).named("absent"),
                MethodType.methodType(Object.class, Object.class));
        try {
            Object ignored = missingProperty.invokeExact((Object) bean);
            System.out.println("missing.property=unexpected:" + ignored);
        } catch (NoSuchDynamicMethodException e) {
            System.out.println("missing.property=" + e.getClass().getSimpleName());
        }

        try {
            Object ignored = construct.invokeExact((Object) bean);
            System.out.println("new.onInstance=unexpected:" + ignored);
        } catch (NoSuchDynamicMethodException e) {
            System.out.println("new.onInstance=" + e.getClass().getSimpleName());
        }

        try {
            Object ignored = call.invokeExact(
                    callable, (Object) bean, (Object) new Object());
            System.out.println("overload.bad=unexpected:" + ignored);
        } catch (NoSuchMethodException e) {
            System.out.println("overload.bad=" + e.getClass().getSimpleName());
        }

        MethodHandle setCountFromObject = link(
                StandardOperation.SET.withNamespace(
                        StandardNamespace.PROPERTY).named("count"),
                MethodType.methodType(
                        void.class, Object.class, Object.class));
        try {
            setCountFromObject.invokeExact((Object) bean, (Object) "7");
            System.out.println("stringToInt=unexpected");
        } catch (ClassCastException e) {
            System.out.println("stringToInt=" + e.getClass().getSimpleName());
        }

        try {
            getColor.invokeExact((Object) bean); // invokeExact expects void here
            System.out.println("wrongDescriptor=unexpected");
        } catch (WrongMethodTypeException e) {
            System.out.println("wrongDescriptor=" + e.getClass().getSimpleName());
        }
    }
}
```

Lệnh biên dịch/run từ thư mục có file:

```bash
javac --release 17 --add-modules jdk.dynalink DynalinkJavaObjectsDemo.java
java --add-modules jdk.dynalink DynalinkJavaObjectsDemo
```

**Vì sao có `--add-modules jdk.dynalink`?** `jdk.dynalink` là module cụ thể của JDK, không phải package trong `java.base`. Với ứng dụng classpath không khai báo `module-info.java`, việc yêu cầu module này tường minh giúp compiler và launcher resolve đúng các public API. Với một **named module** hợp lệ, cần khai báo `requires jdk.dynalink;` trong module descriptor rồi chạy theo module-path/module options phù hợp.

`stdout` **chính xác đã kiểm chứng**:

```text
property=red->blue
shortToInt=7
isDynamicMethod=true
overload.string=text:abc
overload.integer=number:3
explicitSignature=text:xyz
list[1]=two
map.value=42
map.removed=true
array.value=y
array.length=2
record.title=record
static.banner=STATIC
new.class=ColorBean
missing.method=NoSuchDynamicMethodException
missing.property=NoSuchDynamicMethodException
new.onInstance=NoSuchDynamicMethodException
overload.bad=NoSuchMethodException
stringToInt=ClassCastException
wrongDescriptor=WrongMethodTypeException
```

Mã đã được **biên dịch thành công với `javac --release 17`** và thực thi trên **OpenJDK 24**; 20 dòng output khớp. Do môi trường thực thi được kiểm chứng là OpenJDK 24, nếu chạy một vendor/JDK khác, hãy dùng API semantics trong tài liệu Java 17 làm chuẩn và chú ý policy/linker/conversion có thể khác nếu có custom extensions.

### 7.1. Đọc kết quả theo nhóm phép toán

- **`property=red->blue`:** `GET/SET:PROPERTY:color` đã gọi public JavaBean getter/setter dù field nội bộ là private.
- **`shortToInt=7`:** Dynalink thích ứng primitive `short` tại call site thành đối số `int` của setter.
- **`isDynamicMethod=true`:** `GET:METHOD:join` trả object dynamic method do `BeansLinker` nhận biết, không phải kết quả gọi `join`.
- **`overload.string` / `overload.integer`:** `CALL` chọn overload theo runtime types: `String` hoặc `Integer` unbox thành `int`.
- **`explicitSignature=text:xyz`:** operation có tên `join(String)` chọn method signature tường minh; hữu ích khi overload phức tạp/không muốn chọn động.
- **`list[1]=two`, `map.value=42`, `map.removed=true`:** `ELEMENT` là namespace riêng; `REMOVE:ELEMENT` xóa key của `Map`.
- **`array.value=y` / `array.length=2`:** phần tử array được truy cập theo index; `length` là property tổng hợp trong `BeansLinker`.
- **`record.title=record`:** record component accessor được ánh xạ thành property getter.
- **`static.banner=STATIC` / `new.class=ColorBean`:** `StaticClass` đại diện static facet và constructor, không phải Java `Class<?>` thường.
- **Ba dòng `NoSuchDynamicMethodException`:** không có operation/linker phù hợp cho member absent hoặc `NEW` trên instance không phải constructor object.
- **`overload.bad=NoSuchMethodException`:** dynamic method object tìm được, nhưng danh sách overload Java không nhận `new Object()`.
- **`stringToInt=ClassCastException`:** giá trị `"7"` không tự được parse thành số cho setter `int`.
- **`wrongDescriptor=WrongMethodTypeException`:** `invokeExact` của getter trả `Object` lại bị gọi dưới expression context kiểu `void`. Sai descriptor tại caller, không phải lỗi Dynalink không có operation.

## 8. Tại sao một method overload có thể được chọn khác nhau giữa các lần gọi?

Với một method group tên `join`, `GET:METHOD` có thể trả một dynamic method object đại diện cho **nhiều Java overloads**. Lần `CALL` đầu thấy đối số `"abc"`, linker chọn `join(String)`; lần sau thấy `Integer.valueOf(3)`, linker có thể relink hoặc chọn target `join(int)` theo runtime value và conversion rules.

Nói cách khác:

```text
CALL site: (callable, receiver, Object argument) -> Object
       |
       +-- argument runtime String  -> join(String)
       |
       +-- argument runtime Integer -> unbox -> join(int)
       |
       +-- argument runtime Object  -> no applicable overload
                                      -> NoSuchMethodException (ví dụ)
```

Đừng đồng nhất `callSite.type()` với signature của mọi member mà linker sẽ chọn. `MethodType` của call site vẫn cố định, trong khi target được liên kết lại tùy guard và actual argument classes. Một bộ converter do runtime ngôn ngữ cung cấp có thể làm tập overload áp dụng rộng hơn hoặc khác đi; vì thế cần test loại conversion, ambiguity và null.

**Chọn explicit signature:** `GET:METHOD:join(String)` chọn trước `join(String)`. Javadoc `BeansLinker` cho phép tên có dạng signature tường minh, ví dụ `parseInt(String,int)`; tên kiểu đơn giản thường được chấp nhận khi không mơ hồ, còn fully qualified names cần dùng khi hai kiểu trùng simple name.

**Varargs:** `BeansLinker` có hỗ trợ gọi Java varargs methods và constructors. Nhưng không phải mọi lựa chọn overloaded/varargs đều giống cách Java compiler resolve overload tại compile time, bởi runtime value/type conversions có thể khác. Test các ca có overload nhận `Object`, primitive vs wrapper, null, varargs và kết quả error.

## 9. Khi cần điều khiển linker và conversions

`DynamicLinkerFactory` cho cấu hình danh sách `GuardingDynamicLinker`:

1. **Prioritized linkers:** cho runtime ngôn ngữ của bạn ưu tiên object model của nó.
2. **Auto-discovered linkers:** nếu có providers `GuardingDynamicLinkerExporter` được `ServiceLoader` tải.
3. **Fallback linkers:** mặc định có `BeansLinker` nếu bạn chưa thay cấu hình này.

Khi xây runtime JavaScript-like hoặc DSL riêng, bạn có thể đặt linker cho các objects của ngôn ngữ lên trước, để Java object bình thường mới rơi vào `BeansLinker`. Không gọi `BeansLinker` trực tiếp cho mọi thứ khi hệ thống cần nhiều ngôn ngữ/coercion policies; `DynamicLinker` là nơi điều phối.

### 9.1. `setFallbackLinkers` và lỗi do cấu hình

Nếu bạn thay tập fallback bằng danh sách **không chứa BeansLinker**, các thao tác mà trước đó chạy với JavaBean có thể không còn linker nào hỗ trợ. Khi đó `NoSuchDynamicMethodException` có thể xuất hiện ngay cả với Java member public có thật.

Vì vậy khi thấy exception này:

- Kiểm tra **operation**: đã chọn đúng namespace/property/method/element hay chưa?
- Kiểm tra **receiver**: class gì, có thực là `StaticClass` khi muốn `NEW` hoặc static member không?
- Kiểm tra **linker chain**: default `BeansLinker` còn hiện diện không? Custom linker có che mất fallback không?
- Kiểm tra **Lookup** trong `CallSiteDescriptor`: quyền có đủ cho method caller-sensitive hoặc JPMS access không?
- Kiểm tra **MethodType**: `GET:METHOD` thường trả dynamic method object, `CALL` cần receiver và đối số đúng loại.
- Kiểm tra **converters**: thiếu conversion khiến overload không phù hợp, nhưng lỗi cuối có thể là `NoSuchMethodException`/`ClassCastException` chứ không luôn `NoSuchDynamicMethodException`.

Đừng “sửa” bằng cách gọi `setAccessible(true)` mọi member. Dynalink có cơ chế lookup/guards/module riêng; việc lạm dụng reflection không phải giải pháp tổng quát hoặc an toàn.

### 9.2. `MissingMemberHandlerFactory` phải là policy rõ ràng

Nếu ngôn ngữ muốn một operation GET không tồn tại trả `undefined`, hãy thiết kế đúng một sentinel hoặc fallback theo contract. Đừng trả `null` cho cả GET, SET, CALL, NEW không phân biệt — điều đó có thể che các lỗi lập trình hoặc quyền truy cập.

Khi thêm missing-member handler, test riêng:
- đọc property không tồn tại;
- gọi method không tồn tại;
- getter có thật nhưng trả `null`;
- method có thật nhưng nhận sai đối số;
- member không public;
- receiver `null` và các kiểu không hỗ trợ operation.

Các trường hợp này khác nhau về mục đích và nên dẫn đến kết quả khác nhau trong nhiều ngôn ngữ.

## 10. Checklist chẩn đoán theo từng lớp

| Câu hỏi | Cách xem | Nếu có vấn đề |
| --- | --- | --- |
| Operation có namespace đúng? | In `descriptor.getOperation()` | Không lẫn `PROPERTY` với `METHOD` |
| MethodType phù hợp operation? | In `descriptor.getMethodType()` hoặc `handle.type()` | Sửa số lượng/kiểu receiver, name, value, return |
| Receiver thật là gì? | `receiver.getClass()` nếu không null | Dùng đúng Java object hoặc `StaticClass` |
| Member có public và nhìn thấy từ caller không? | So Java API visibility, module exports | Không suy private luôn được mở |
| Linker có hỗ trợ Java objects không? | Xem cấu hình `DynamicLinkerFactory` | Giữ `BeansLinker` fallback khi cần |
| Có overload nào nhận actual argument types không? | Xem Java method signatures; `GET:METHOD`/`CALL` | Chuyển đổi hợp lệ hoặc explicit signature |
| Có conversion từ source type sang target type không? | Xem `LinkerServices.canConvert`/custom strategy | Không tự parse String số nếu không có converter |
| Exception phát sinh ở giai đoạn nào? | Stack trace, cause và loại exception | Phân biệt link, adapt, invokeExact, target execution |
| Guard bị invalidated khi receiver đổi? | Quan sát loại receiver khác nhau và cache policy | Chọn `ChainedCallSite`/cache strategy phù hợp |
| Method của chính ứng dụng ném lỗi? | Tìm stack trace vào method Java thực | Không đổi linker khi lỗi thuộc business logic |

**Debug theo thứ tự tối thiểu**: ghi operation, `MethodType`, receiver runtime class, method signatures/candidate conversions và exception/cause. Đừng lạm dụng logging khi script chạy với thông tin nhạy cảm; log metadata, che/ẩn giá trị cần bảo mật.

Ví dụ kiểm tra API có ích:

```java
System.out.println("type=" + getColor.type());
System.out.println("properties="
        + BeansLinker.getReadableInstancePropertyNames(ColorBean.class));
System.out.println("methods="
        + BeansLinker.getInstanceMethodNames(ColorBean.class));
```

Đoạn này là ví dụ **ngữ cảnh**, dùng biến `getColor` và class `ColorBean` đã có ở chương trình mục 7. `Set` các tên public được trả về có thể có cả thành viên kế thừa; không nên hard-code toàn bộ danh sách làm output chuẩn.

## 11. Thiết kế ứng dụng: dùng đúng công cụ, không “động hóa” mọi thứ

**Dùng Dynalink khi** bạn đang viết runtime/DSL hoặc bộ liên kết hoạt động trên objects mà type không biết lúc compile, cần dispatch qua nhiều object models, muốn guard/relink và có policies overload/conversion.

**Không nhất thiết dùng Dynalink khi** Java code đã biết `ColorBean` và chỉ cần gọi `bean.getColor()`: Java compiler/JVM sẽ dùng method invocation thông thường đơn giản hơn. Dynalink không phải thay thế mặc định cho mọi reflection hay `MethodHandle`.

### 11.1. Kiểu trả về, null và exceptions

Kết quả của dynamic property/method call có thể là `null` nếu member thực sự trả null hoặc một fallback cố ý làm vậy. Khi code client phải unbox primitive, null có thể dẫn tới `NullPointerException`. Đây không tự chứng minh linker không tìm được method.

Nếu target Java ném exception nghiệp vụ, đừng tự động chuyển mọi lỗi thành `NoSuchDynamicMethodException`; exception này có ý nghĩa **không link được call site**, không phải “thực thi thất bại nói chung”.

### 11.2. Concurrency và cache

Call site có thể relink khi gặp types mới. Việc giữ một `MethodHandle` dynamic invoker không đồng nghĩa mọi mutable Java object đã thread-safe. State của `ColorBean`, `List`, `Map` và custom linkers vẫn cần concurrency discipline riêng (locks, immutable snapshots, concurrent collections...). `ChainedCallSite` có thể cải thiện cache cho nhiều receiver classes, nhưng không phải cơ chế synchronization của object state.

### 11.3. An toàn và quyền truy cập

Dynamic linking cho phép script/ngôn ngữ động **khám phá và gọi các Java methods public** theo khả năng của linker; đó không phải sandbox. Nếu expose objects có methods nhạy cảm cho script không tin cậy, policy cần giới hạn objects/members, không dựa vào việc caller chưa biết tên method. `MethodHandles.Lookup` có thể mang quyền khác nhau; caller-sensitive methods đòi lookup đủ mạnh theo Javadoc `BeansLinker`. Một runtime production nên kiểm tra trust boundary, JPMS exports, deserialization, resource limits và audit, đồng thời hạn chế object graph được expose.

## 12. Bài tập tự kiểm tra

**A.** `GET:PROPERTY:color` và `GET:METHOD:color` có tương đương không? Nếu muốn gọi `bean.join("x")` qua Dynalink thì gồm những operation nào?

**B.** `SET:PROPERTY:count` có target setter `setCount(int)`. Call-site value descriptor kiểu `short`, truyền `(short) 7`. Có hợp lệ không? Vì sao?

**C.** Cùng setter `int`, nhưng truyền `"7"` dưới dạng `Object`. API có cam kết sẽ parse string thành int không? Ví dụ lỗi gì?

**D.** `GET:METHOD:absent` trên JavaBean không có method. Với `BeansLinker` mặc định và không có custom fallback, loại lỗi nào xuất hiện ở invocation?

**E.** `GET:METHOD:join` thành công trả dynamic method object. `CALL` truyền `new Object()` trong khi chỉ có `join(String)` và `join(int)`. Vì sao có thể là `NoSuchMethodException` chứ không phải `NoSuchDynamicMethodException`?

**F.** Dùng `StandardOperation.NEW` trên `ColorBean.class` hoặc một `ColorBean` instance có đúng cách làm như `NEW` trên `StaticClass.forClass(ColorBean.class)` không?

**G.** `getColor` có MethodType `(Object)Object`. Gọi `getColor.invokeExact((Object) bean);` như statement có thể lỗi gì? Tại sao?

**H.** `record Box(String title)` không có method `getTitle()`. `BeansLinker` có thể expose `title` như property getter không?

**I.** Một language runtime custom vừa thay tập fallback linkers làm mất `BeansLinker`, và các operation Java object bắt đầu thất bại. Kiểm tra gì trước khi kết luận JavaBean class lỗi?

**J.** `List` và `Map` đều dùng namespace `ELEMENT`. Key/index và semantics remove có tự động giống nhau không? Vì sao?

### Đáp án

- **A:** Không. `PROPERTY` đọc property getter/field; `METHOD` lấy dynamic method object. Để gọi `join`, dùng `GET:METHOD:join` rồi `CALL(callable, receiver, args...)`.
- **B:** Có theo ví dụ: primitive widening `short` → `int` là conversion hợp lệ; `BeansLinker` chọn setter.
- **C:** Không. `"7"` không tự parse thành `int`; ví dụ kiểm thử ném `ClassCastException`.
- **D:** `NoSuchDynamicMethodException` tại lúc invoke, nếu không linker nào có thể link operation.
- **E:** Đã có dynamic method object; lỗi xảy ra khi chọn overload cho argument không phù hợp, trong ví dụ là `NoSuchMethodException`.
- **F:** Không. Muốn static methods/constructors, dùng `StaticClass`. Java `Class<?>` là object thường; `NEW` trên Java instance không có ý nghĩa constructor theo `BeansLinker`.
- **G:** `WrongMethodTypeException` vì descriptor `invokeExact` trong statement context trả `void`, khác return type `Object` của handle.
- **H:** Có. BeansLinker Java 17 expose public record component accessors như property getters.
- **I:** Kiểm tra `DynamicLinkerFactory`, prioritized/autoloaded/fallback linkers và việc bỏ BeansLinker; cũng kiểm tra operation/Lookup/conversion.
- **J:** Không. `List` dùng index, `Map` dùng key; `REMOVE:ELEMENT` có semantics của container tương ứng, không biến array thành cấu trúc có thể xóa phần tử.

## 13. Tài liệu chính thức Java 17

- [Oracle JDK 17 — module `jdk.dynalink`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html): mô hình Dynalink, `RelinkableCallSite`, object property operations và fallback Java linker.
- [Oracle JDK 17 — `BeansLinker`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/beans/BeansLinker.html): JavaBean properties, public fields, records, arrays/List/Map, dynamic methods, overloaded resolution, missing members.
- [Oracle JDK 17 — `StaticClass`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/beans/StaticClass.html): static facet và constructor operation.
- [Oracle JDK 17 — `StandardOperation`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/StandardOperation.html): `GET`, `SET`, `REMOVE`, `CALL` và `NEW` cùng chữ ký.
- [Oracle JDK 17 — `DynamicLinkerFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html): prioritized, autodiscovered và fallback linkers, conversion strategy.
- [Oracle JDK 17 — `NoSuchDynamicMethodException`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/NoSuchDynamicMethodException.html): runtime exception khi không linker khả dụng nào link được call site.
- [Oracle JDK 17 — `LinkerServices`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/LinkerServices.html): `asType`, `canConvert`, `compareConversion` và language-specific converter support.
- [Oracle JDK 17 — `MethodHandle.invokeExact`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): signature-polymorphic invocation và `WrongMethodTypeException`.

**Ghi nhớ:** `BeansLinker` giúp Dynalink liên kết operations trên Java objects với getter/setter, method, element và constructor. `LinkerServices` có thể thích ứng kiểu và dùng converters của runtime, nhưng không cam kết ép kiểu tùy ý. **`NoSuchDynamicMethodException` có nghĩa không link được dynamic operation tại invocation**; lỗi chọn overload, chuyển đổi đối số, sai `invokeExact` hoặc lỗi từ method Java thực phải được chẩn đoán riêng.
