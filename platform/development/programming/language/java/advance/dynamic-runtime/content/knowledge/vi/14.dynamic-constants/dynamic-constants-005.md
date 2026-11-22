# 14.5. ConstantDesc, ClassDesc, MethodTypeDesc và MethodHandleDesc

> **Phạm vi:** Bài Knowledge của nhóm **14. Hằng động** trong **Java Advance – dynamic-runtime**, dựa trên Java SE 21. Trọng tâm là bộ API `java.lang.constant`: `ConstantDesc` là **mô tả danh nghĩa** (*nominal descriptor*), `ClassDesc` mô tả lớp, `MethodTypeDesc` mô tả kiểu phương thức, `MethodHandleDesc` mô tả method handle. Chúng có thể được **xây dựng, so sánh, phân tích trước khi class/method tồn tại hoặc được resolve**, rồi mới giải quyết trong ngữ cảnh quyền truy cập `MethodHandles.Lookup`. Bài cũng nối chúng với `DynamicConstantDesc` và constant pool (`CONSTANT_Dynamic`), nhưng không đánh đồng việc tạo Java object mô tả với việc sinh class file.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **giá trị runtime** (`Class<?>`, `MethodType`, `MethodHandle`) với **nominal descriptor** (`ClassDesc`, `MethodTypeDesc`, `MethodHandleDesc`).
2. Giải thích `ConstantDesc.resolveConstantDesc(lookup)` dùng **Lookup context**, bao gồm class loading, module và access checks, thay vì chỉ parse một chuỗi.
3. Tạo `ClassDesc` bằng `of`, `ofDescriptor`, `ofInternalName`, `arrayType`; đọc chính xác *field descriptor* và internal name.
4. Tạo và biến đổi `MethodTypeDesc` bằng `of`, `ofDescriptor`, `changeReturnType`, `insertParameterTypes`, `descriptorString`; nhận biết erased types và giới hạn runtime.
5. Dùng `MethodHandleDesc.ofMethod`, `ofConstructor` và `ofField` với đúng `DirectMethodHandleDesc.Kind`; phân biệt **lookup descriptor** với **invocation type**.
6. Resolve một method-handle descriptor với `Lookup` phù hợp rồi gọi qua `invokeExact`; hiểu lỗi do thiếu class, thiếu member, sai loại/kiểu và thiếu quyền.
7. Mô tả sự liên hệ với `Constable.describeConstable()`, `ConstantDescs`, `DynamicConstantDesc` và bootstrap method của `CONSTANT_Dynamic`.
8. Tự chạy năm chương trình Java 21 độc lập, kiểm chứng stdout và biết vì sao **cùng nominal description nhưng khác lookup context** có thể có kết quả khác.

**Kiến thức nền:** JVM field/method descriptor, `Class<?>`, Reflection, `MethodHandles.Lookup`, static/virtual method, constructor, field, class loader, JPMS và Java generics/erasure ở mức cơ bản. Không cần ASM/Byte Buddy hoặc JDK internal APIs. Ví dụ dùng `javac --release 21` và API có trong Java 21.

## 2. Tại sao JVM cần nominal descriptors?

Trong bytecode, một `CONSTANT_Class_info` mô tả class bằng tên; `CONSTANT_MethodType_info` mô tả một method type bằng chuỗi method descriptor; `CONSTANT_MethodHandle_info` chỉ tới method/constructor/field cùng *reference kind*. `CONSTANT_Dynamic_info` lại mô tả **một giá trị sẽ được tính lúc resolution bằng bootstrap method**. Các constant pool entries là thông tin dạng ký hiệu; chúng không mang sẵn `Class<?>` hoặc `MethodHandle` đã link của tiến trình Java cụ thể.

`java.lang.constant` (Java 12+) cung cấp các **Java objects diễn tả** những mô tả đó, rất tiện cho bytecode readers/writers, code generation, constant-pool analysis, runtime metadata và kiểm tra trước khi link. Theo package Javadoc, một `ConstantDesc` là **recipe for a constant value**: có thể kiểm tra recipe, giữ nó, rồi resolve khi có ngữ cảnh phù hợp.

```text
JVM symbolic information                      Runtime objects
------------------------                      ---------------------------
ClassDesc("java.lang.String")     -- Lookup --> java.lang.String.class
MethodTypeDesc("(I)String")       -- Lookup --> MethodType(int -> String)
MethodHandleDesc(owner/name/kind) -- Lookup --> MethodHandle đã link
DynamicConstantDesc(BSM, name...) -- Lookup --> giá trị BSM trả về

                  resolveConstantDesc(lookup)
                  + class loading/module access
                  + member lookup/linkage (tùy loại)
```

Dòng biểu diễn `"(I)String"` trong sơ đồ là **ký pháp dễ đọc**, không phải chuỗi JVM method descriptor hợp lệ. Chuỗi JVM thực cho `String m(int)` là `(I)Ljava/lang/String;`.

**Điểm then chốt:** `ClassDesc.of("com.acme.Widget")` **không** tải ngay `com.acme.Widget`. `MethodHandleDesc.ofMethod(...)` **không** tự tìm/gọi method. Các factory tạo đối tượng *descriptor*; thao tác `resolveConstantDesc(lookup)` mới yêu cầu runtime value. Chạy `resolveConstantDesc` bằng Lookup khác có thể thất bại hoặc nhận runtime types khác.

## 3. Bốn khái niệm chính và quan hệ của chúng

| API | Nominal description cho | Đầu vào/metadata chính | Kết quả `resolveConstantDesc(lookup)` |
| --- | --- | --- | --- |
| `ConstantDesc` | Giao diện chung của hằng có thể mô tả | Hợp đồng giải quyết trong `Lookup` | `Object` (subtype thường trả kiểu chuyên biệt) |
| `ClassDesc` | Kiểu lớp, interface, primitive, mảng, void | JVM field-type descriptor hoặc tên lớp danh nghĩa | `Class<?>` |
| `MethodTypeDesc` | Return + ordered parameter types | `ClassDesc` và JVM method descriptor | `MethodType` |
| `MethodHandleDesc` | Một method/constructor/field handle | Owner `ClassDesc`, name, reference kind, type | `MethodHandle` |

Tính chất quan trọng:

- `ConstantDesc` trong Java 21 là **sealed interface**, với các nhánh được JDK quy định. Các kiểu `ClassDesc`, `MethodTypeDesc` và `MethodHandleDesc` đều là `ConstantDesc`; `DirectMethodHandleDesc` là subtype chuyên cho direct handles.
- `String`, `Integer`, `Long`, `Float`, `Double` là các kiểu hằng native có thể **tự làm `ConstantDesc`** cho chính giá trị của chúng. **Không suy** rằng mọi boxed primitive hay mọi object đều trực tiếp implement `ConstantDesc`.
- Các constant descriptors được thiết kế theo nguyên tắc **immutable**; so sánh ý nghĩa bằng `equals`, **không** bằng `==`, vì JDK không bảo đảm một descriptor được intern thành một instance duy nhất.
- Một `ConstantDesc` không phải lời hứa rằng mọi lần resolve luôn thành công. Runtime environment có thể thiếu class, bị hạn chế quyền hoặc không biểu diễn được một kiểu dù nominal descriptor hợp lệ.
- Một Java object descriptor **không tự tạo** thêm `CONSTANT_*` entry trong class file: công việc phát sinh bytecode cần một compiler hoặc bytecode writer riêng.

### 3.1. So sánh “mô tả” và “đã được resolve”

| Điều cần hỏi | Nominal descriptor | Runtime counterpart |
| --- | --- | --- |
| “Tên class là gì?” | `ClassDesc.descriptorString()` | `Class.getName()` hoặc `getTypeName()` |
| “Mảng có component gì?” | `ClassDesc.componentType()` | `Class.getComponentType()` |
| “Method nhận/trả những kiểu nào?” | `MethodTypeDesc.parameterType(i)`, `returnType()` | `MethodType.parameterType(i)`, `returnType()` |
| “Handle gọi method/field nào?” | `DirectMethodHandleDesc.owner()`, `methodName()`, `kind()` | `MethodHandle`, `revealDirect` nếu đủ quyền |
| “Có quyền truy cập không?” | Chưa kết luận chỉ từ descriptor | `resolveConstantDesc(lookup)` và các kiểm tra runtime |
| “Hai kiểu cùng tên có cùng identity không?” | Cùng nominal name có thể `equals=true` | Có thể **khác `Class<?>`** nếu loaders khác nhau |

`MethodTypeDesc` không phải phiên bản “thay tên” của `MethodType` trong mọi ngữ cảnh; nominal information tách khỏi runtime resolution và chịu ràng buộc JVM khác nhau.

## 4. `ConstantDesc`: giao diện của recipe và resolve

Cốt lõi của `ConstantDesc` là:

```java
// Chữ ký rút gọn từ API, không phải một interface khai báo đầy đủ.
Object resolveConstantDesc(MethodHandles.Lookup lookup)
        throws ReflectiveOperationException;
```

Một `lookup` mang theo **lookup class**, class loader và **access modes**, giúp giải quyết các tên class/member theo quy tắc JVM/JPMS. Kết quả là giá trị thực của hằng:

- Với `ClassDesc`: một `Class<?>` như `String.class`.
- Với `MethodTypeDesc`: một `MethodType` có parameter/return `Class<?>` cụ thể.
- Với `MethodHandleDesc`: một `MethodHandle` đã resolve, sẵn sàng để invoke theo signature hợp lệ.
- Với `DynamicConstantDesc<T>`: giá trị do bootstrap method tính ra, có thể là `null` khi loại/BSM cho phép.
- Với `"hello"` hoặc `Integer.valueOf(7)`: bản thân native constant value.

Không tự catch mỗi `ReflectiveOperationException` rồi coi như “không có descriptor”; mô tả vẫn có thể đúng cú pháp. Phân loại ít nhất: **syntax/shape**, **class resolution**, **access**, **member lookup**, **linkage**, **invocation**.

### 4.1. Lookup context không được serialize vào descriptor

Hai class loaders có thể định nghĩa hai `com.acme.Message` có cùng binary name. `ClassDesc.of("com.acme.Message")` là cùng nominal description, nhưng resolve qua Lookup từ những loader khác nhau có thể trả **hai đối tượng `Class<?>` khác identity**, hoặc thất bại nếu một bên không thấy class. Một `MethodTypeDesc` hay `MethodHandleDesc` chứa `ClassDesc` đó cũng thừa hưởng yếu tố ngữ cảnh này.

**Không dùng duy nhất descriptor string làm khóa cache runtime** xuyên plugins/module layers. Nếu cần cache sau resolution, phân vùng theo `Lookup`/loader/module và quyền phù hợp, hoặc dùng chính runtime class/member identity.

### 4.2. Resolution không đồng nghĩa caching

Theo Javadoc, `resolveConstantDesc` **không tự bảo đảm cache kết quả cho riêng descriptor object**. Một số runtime entities (`Class<?>`, `MethodType`) có đặc trưng chia sẻ/cache ở tầng JVM, nhưng contract của descriptor không dựa vào identity của những lần resolve. Nếu tối ưu cache, phải thiết kế rõ scope, lifecycle và khả năng class loader bị giữ sống.

## 5. `ClassDesc`: từ class name đến field descriptor

`ClassDesc` diễn tả kiểu trong cùng ngôn ngữ ký hiệu như JVM `field descriptor` (`ClassDesc` còn cho phép mô tả `void`). Những cách tạo thông dụng:

| Lời gọi | Nominal type | `descriptorString()` |
| --- | --- | --- |
| `ClassDesc.of("java.lang.String")` | `String` | `Ljava/lang/String;` |
| `ClassDesc.ofInternalName("java/lang/String")` | `String` | `Ljava/lang/String;` |
| `ClassDesc.ofDescriptor("Ljava/lang/String;")` | `String` | `Ljava/lang/String;` |
| `ConstantDescs.CD_int` | primitive `int` | `I` |
| `ConstantDescs.CD_void` | `void` | `V` |
| `ClassDesc.ofDescriptor("[I")` | `int[]` | `[I` |
| `ClassDesc.of("java.lang.String").arrayType(2)` | `String[][]` | `[[Ljava/lang/String;` |
| `ClassDesc.of("java.util.Map$Entry")` | nested `Map.Entry` | `Ljava/util/Map$Entry;` |

**Tên khác nhau cho những mục đích khác nhau:**

1. `of("java.lang.String")` nhận **binary name dạng dấu chấm** của class/interface.
2. `ofInternalName("java/lang/String")` nhận **internal name dạng dấu slash**, thường lấy từ bytecode.
3. `ofDescriptor("Ljava/lang/String;")` nhận **một field type descriptor đầy đủ**; cũng áp dụng cho primitive/array. Không đưa chuỗi phương thức `(I)V` vào `ClassDesc.ofDescriptor`.
4. `arrayType()` thêm một `[`; `arrayType(2)` thêm hai chiều; `componentType()` loại bỏ một chiều của mảng.
5. `displayName()` là **giao diện hiển thị cho người**, không phải JVM descriptor, và tên lớp không được bảo đảm unique khi thiếu package.

### 5.1. Tham chiếu class lồng nhau

Trong JVM internal name, package separators dùng `/`, còn nested/member classes dùng ký tự `$` trong binary name:

```text
Java source:     java.util.Map.Entry
Binary name:     java.util.Map$Entry
Internal name:   java/util/Map$Entry
Field descriptor: Ljava/util/Map$Entry;
```

Không đưa `java.util.Map.Entry` vào `ClassDesc.of` như tên binary chính xác của nested class. Java source spelling và JVM binary name không giống nhau trong trường hợp này.

### 5.2. Type erasure và giới hạn generic

`ClassDesc` không có constructor cho `List<String>` như một class riêng biệt. Class file dùng runtime type `java.util.List` sau erasure; generic type arguments (nếu có) được lưu ở `Signature` attribute hoặc metadata khác, không trong `ClassDesc`.

Ví dụ `ClassDesc.of("java.util.List")` biểu diễn raw runtime class, **không** thể chứng minh từ đó phần tử luôn là `String`. Nếu cần phân tích generic declaration, dùng `java.lang.reflect.Type` hoặc class-file signature parser riêng.

## 6. Lab 1 — ClassDesc và resolution không thành công

Tạo file độc lập **`ClassDescLab.java`**:

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.invoke.MethodHandles;

public class ClassDescLab {
    public static void main(String[] args) throws ReflectiveOperationException {
        ClassDesc string = ClassDesc.of("java.lang.String");
        ClassDesc fromInternal = ClassDesc.ofInternalName("java/lang/String");
        ClassDesc matrix = string.arrayType(2);
        ClassDesc nested = ClassDesc.of("java.util.Map$Entry");
        ClassDesc absent = ClassDesc.of("demo.missing.NotHere");

        System.out.println("string=" + string.descriptorString());
        System.out.println("sameNominal=" + string.equals(fromInternal));
        System.out.println("matrix=" + matrix.descriptorString());
        System.out.println("matrixDisplay=" + matrix.displayName());
        System.out.println("component=" + matrix.componentType().descriptorString());
        System.out.println("nested=" + nested.descriptorString());
        System.out.println("primitive=" + ConstantDescs.CD_int.descriptorString());
        System.out.println("void=" + ConstantDescs.CD_void.descriptorString());
        System.out.println("resolvedString=" +
                (string.resolveConstantDesc(MethodHandles.lookup()) == String.class));
        System.out.println("classDescribed=" + String.class.describeConstable().isPresent());
        System.out.println("absentNominal=" + absent.descriptorString());
        try {
            absent.resolveConstantDesc(MethodHandles.lookup());
            System.out.println("absentResolve=unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("absentResolve=ClassNotFoundException");
        }
    }
}
```

Chạy từ terminal với JDK có hỗ trợ Java 21:

```sh
javac --release 21 -Xlint:all ClassDescLab.java
java ClassDescLab
```

**Stdout:**

```text
string=Ljava/lang/String;
sameNominal=true
matrix=[[Ljava/lang/String;
matrixDisplay=String[][]
component=[Ljava/lang/String;
nested=Ljava/util/Map$Entry;
primitive=I
void=V
resolvedString=true
classDescribed=true
absentNominal=Ldemo/missing/NotHere;
absentResolve=ClassNotFoundException
```

### 6.1. Tại sao kết quả có ý nghĩa?

- Hai cách tạo descriptor `of` và `ofInternalName` cho cùng loại danh nghĩa nên `equals` trả `true`.
- `String[][]` được mã hóa `[[Ljava/lang/String;`; component một chiều là `[Ljava/lang/String;`.
- `CD_int` và `CD_void` là nominal primitive/void descriptors có sẵn trong `ConstantDescs`.
- `String.class.describeConstable()` trả một `Optional<ClassDesc>` có giá trị vì `String` là kiểu có thể mô tả danh nghĩa.
- `ClassDesc.of("demo.missing.NotHere")` vẫn tạo được **mô tả hợp lệ**, không nạp lớp. Chỉ khi `resolveConstantDesc(lookup)` chạy, yêu cầu resolve class không tồn tại mới thất bại với `ClassNotFoundException`.

### 6.2. “Tạo được ClassDesc” không phải “load được Class”

Ngay cả một tên hợp lệ về mặt descriptor vẫn có thể không tồn tại trong class loader, bị chặn theo module access hoặc tham chiếu dependency lỗi. Đó là lý do các thư viện phân tích bytecode thường dùng danh nghĩa trước, và trì hoãn resolution cho tới khi có môi trường runtime thích hợp.

## 7. `MethodTypeDesc`: method descriptor dưới dạng các ClassDesc

JVM method descriptor có cấu trúc:

```text
MethodDescriptor = "(" {ParameterDescriptor} ")" ReturnDescriptor
ParameterDescriptor = FieldType
ReturnDescriptor    = FieldType | V
FieldType           = BaseType | ObjectType | ArrayType
```

Primitive codes gồm `B`, `C`, `D`, `F`, `I`, `J`, `S`, `Z`; object type là `Linternal/name;`; array type có tiền tố `[`. `V` chỉ hợp lệ ở return; không thể có `void` parameter.

`MethodTypeDesc` cung cấp các factory chính:

- `MethodTypeDesc.of(returnClassDesc, paramClassDescs...)`: xây từ nominal types có sẵn.
- `MethodTypeDesc.ofDescriptor("(I[Ljava/lang/String;)Ljava/lang/String;")`: parse một JVM method descriptor **không bắt buộc tải các class**.
- `descriptorString()`: xuất dạng JVM, ví dụ `(I)Ljava/lang/String;`.
- `displayDescriptor()`: xuất dạng dễ đọc, ví dụ `(int,String[])String`; **không đưa display text vào parser JVM**.
- `returnType()`, `parameterType(i)`, `parameterCount()` và `parameterList()`: phân tích cấu trúc.
- `changeReturnType(...)`, `changeParameterType(...)`, `dropParameterTypes(...)`, `insertParameterTypes(...)`: tạo **descriptor mới**, không sửa object cũ.
- `resolveConstantDesc(lookup)`: tạo một `MethodType` runtime nếu có thể resolve tất cả referenced classes và type hợp lệ.

### 7.1. Phân biệt MethodTypeDesc với MethodType

| `MethodTypeDesc` | `MethodType` |
| --- | --- |
| Chứa `ClassDesc` danh nghĩa cho các kiểu | Chứa `Class<?>` runtime cho return/parameters |
| Có thể tồn tại khi referenced class chưa được nạp | Muốn có runtime `Class<?>` phải resolve class |
| Không gắn class loader trực tiếp vào tên | Runtime class identity chịu class loader/module |
| `displayDescriptor()`/`descriptorString()` | `toString()`/`toMethodDescriptorString()` |
| Tạo trước cho bytecode generation, metadata | Dùng trực tiếp trong MethodHandles/Lookup runtime |

`MethodTypeDesc` còn có thể mô tả một method descriptor **không representable bằng `MethodType`**, ví dụ vượt 255 parameter slots theo JVM; Javadoc cảnh báo resolve những descriptor như vậy có thể thất bại. Vì thế **parse thành công chưa có nghĩa một JVM method runtime với chữ ký đó có thể tồn tại**.

### 7.2. Không có generics ở JVM method descriptor

`List<String> transform(List<Integer> source)` có descriptor sau erasure:

```text
(Ljava/util/List;)Ljava/util/List;
```

`MethodTypeDesc` không phân biệt `List<Integer>` và `List<String>` như hai `ClassDesc` runtime khác nhau. Khi cần generic signature, dùng `Signature` attribute và Reflection `getGenericReturnType()`/`getGenericParameterTypes()`.

## 8. Lab 2 — tạo, biến đổi và resolve MethodTypeDesc

Tạo **`MethodTypeDescLab.java`**:

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.MethodTypeDesc;
import java.lang.invoke.MethodType;
import java.lang.invoke.MethodHandles;

public class MethodTypeDescLab {
    public static void main(String[] args) throws ReflectiveOperationException {
        ClassDesc words = ClassDesc.of("java.lang.String").arrayType();
        MethodTypeDesc nominal = MethodTypeDesc.of(
                ConstantDescs.CD_String, ConstantDescs.CD_int, words);
        MethodTypeDesc parsed =
                MethodTypeDesc.ofDescriptor("(I[Ljava/lang/String;)Ljava/lang/String;");
        MethodTypeDesc extended =
                nominal.insertParameterTypes(1, ConstantDescs.CD_long);
        MethodTypeDesc changed =
                nominal.changeReturnType(ConstantDescs.CD_void);
        MethodType actual = nominal.resolveConstantDesc(MethodHandles.lookup());

        System.out.println("descriptor=" + nominal.descriptorString());
        System.out.println("equalParsed=" + nominal.equals(parsed));
        System.out.println("display=" + nominal.displayDescriptor());
        System.out.println("parameters=" + nominal.parameterCount());
        System.out.println("return=" + nominal.returnType().descriptorString());
        System.out.println("extended=" + extended.descriptorString());
        System.out.println("changedReturn=" + changed.descriptorString());
        System.out.println("resolved=" + actual.toMethodDescriptorString());
        System.out.println("describedBack=" +
                actual.describeConstable().orElseThrow().equals(nominal));
        try {
            MethodTypeDesc.ofDescriptor("(V)I");
            System.out.println("invalid=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid=IllegalArgumentException");
        }
        MethodTypeDesc missing = MethodTypeDesc.ofDescriptor("(Ldemo/missing/Never;)V");
        System.out.println("missingNominal=" + missing.descriptorString());
        try {
            missing.resolveConstantDesc(MethodHandles.lookup());
            System.out.println("missingResolve=unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("missingResolve=ClassNotFoundException");
        }
    }
}
```

Chạy:

```sh
javac --release 21 -Xlint:all MethodTypeDescLab.java
java MethodTypeDescLab
```

**Stdout:**

```text
descriptor=(I[Ljava/lang/String;)Ljava/lang/String;
equalParsed=true
display=(int,String[])String
parameters=2
return=Ljava/lang/String;
extended=(IJ[Ljava/lang/String;)Ljava/lang/String;
changedReturn=(I[Ljava/lang/String;)V
resolved=(I[Ljava/lang/String;)Ljava/lang/String;
describedBack=true
invalid=IllegalArgumentException
missingNominal=(Ldemo/missing/Never;)V
missingResolve=ClassNotFoundException
```

### 8.1. Những chi tiết dễ bị bỏ qua

- `MethodTypeDesc.of` nhận **return trước**, tiếp theo là các parameter types theo thứ tự. Trong descriptor string, return được ghi **sau** dấu `)`. Đừng đảo hai conventions.
- `insertParameterTypes(1, CD_long)` chèn `long` trước tham số `String[]` ở index 1; kết quả `(IJ[Ljava/lang/String;)Ljava/lang/String;`.
- `changed` trả `void` nhưng giữ nguyên tham số; `nominal` không bị thay đổi vì descriptor immutable.
- `displayDescriptor()` là readable representation, không phải đầu vào `MethodTypeDesc.ofDescriptor`.
- `actual.describeConstable().orElseThrow()` trả nominal descriptor nếu method type có thể mô tả; trong thí nghiệm các class đều là kiểu JDK danh nghĩa nên round-trip thành công.
- `(V)I` lỗi cú pháp (`void` không thể là parameter), còn `(Ldemo/missing/Never;)V` **đúng cú pháp** nhưng resolve runtime bị `ClassNotFoundException`.

## 9. `MethodHandleDesc`: mô tả handle cho method, constructor và field

`MethodHandleDesc` là nominal descriptor của `MethodHandle`. Thường bạn tạo một `DirectMethodHandleDesc` qua các factory của interface:

```java
// API minh họa; không phải ví dụ hoàn chỉnh.
MethodHandleDesc.ofMethod(kind, owner, methodName, lookupMethodType);
MethodHandleDesc.ofConstructor(owner, constructorParamTypes...);
MethodHandleDesc.ofField(kind, owner, fieldName, fieldType);
```

Ở đây:

- `owner` là `ClassDesc` của class/interface sở hữu member.
- `kind` là `DirectMethodHandleDesc.Kind`: quyết định thao tác là static/virtual/special, constructor hay field getter/setter.
- `methodName` là unqualified method name; với constructor dùng `ofConstructor` để tránh phải tự điền `<init>`.
- `lookupMethodType` là `MethodTypeDesc` của **method khai báo được dùng cho lookup**, *không chứa receiver* đối với virtual method.
- `fieldType` là **ClassDesc của field**, không phải method descriptor.
- `invocationType()` là `MethodTypeDesc` của **handle khi gọi** — có thể khác lookup type vì receiver và constructor return.
- `resolveConstantDesc(lookup)` dùng member resolution, class visibility và access checks để tạo `MethodHandle`.

### 9.1. Các Kind quan trọng

| `DirectMethodHandleDesc.Kind` | Ý nghĩa | Tương ứng Lookup/JVM |
| --- | --- | --- |
| `STATIC` | Class static method | `findStatic` / `invokestatic` |
| `INTERFACE_STATIC` | Interface static method | `findStatic` / `invokestatic` |
| `VIRTUAL` | Instance class method | `findVirtual` / `invokevirtual` |
| `INTERFACE_VIRTUAL` | Instance interface method | `findVirtual` / `invokeinterface` |
| `SPECIAL` | Special invocation | `findSpecial` / `invokespecial` |
| `INTERFACE_SPECIAL` | Special interface invocation | `findSpecial` / `invokespecial` |
| `CONSTRUCTOR` | Constructor | `findConstructor` / `new` + `<init>` |
| `GETTER`, `SETTER` | Instance field read/write | `getfield`, `putfield` |
| `STATIC_GETTER`, `STATIC_SETTER` | Static field read/write | `getstatic`, `putstatic` |

`Kind` phải phù hợp loại owner/method/field; một descriptor có thể hợp lệ về cú pháp nhưng không thể resolve member trong Lookup context thực tế.

### 9.2. Lookup descriptor khác invocation type

Xét `Target.decorate(String):String` là instance method:

```text
Owner:           MethodHandleDescLab$Target
Lookup type:     (Ljava/lang/String;)Ljava/lang/String;
Invocation type: (LMethodHandleDescLab$Target;Ljava/lang/String;)Ljava/lang/String;
                 ^ receiver được chèn vào đầu khi gọi handle
```

Method descriptor của method instance trong class file không chứa `this`. Nhưng `MethodHandle` đã resolve cần nhận receiver làm một tham số ở đầu.

Với constructor `Target(int)`:

```text
Constructor trong JVM:   (I)V       // <init> có return void
Constructor handle:      (I)LMethodHandleDescLab$Target;
```

`MethodHandleDesc.ofConstructor(owner, CD_int)` tự xây description cho constructor invocation; `invocationType()` sẽ trả kiểu **instance mới**, không phải `void`.

Với field:

```text
Instance getter String label: (LTarget;)Ljava/lang/String;
Static getter int shared:    ()I
Instance setter String label: (LTarget;Ljava/lang/String;)V
Static setter int shared:    (I)V
```

`LTarget;` trong bảng field là viết tắt để minh họa; JVM descriptor thực phải dùng đầy đủ **internal name** của declaring class. Đừng đưa một `MethodTypeDesc` vào `ofField` ở chỗ factory yêu cầu `ClassDesc`.

## 10. Lab 3 — STATIC, VIRTUAL, CONSTRUCTOR và FIELD descriptions

Tạo file **`MethodHandleDescLab.java`**:

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DirectMethodHandleDesc;
import java.lang.constant.MethodHandleDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

public class MethodHandleDescLab {
    public static class Target {
        public String label;
        public static int shared = 11;

        public Target(int value) {
            this.label = "v" + value;
        }
        public static int add(int a, int b) {
            return a + b;
        }
        public String decorate(String text) {
            return "[" + text + "]";
        }
    }

    public static void main(String[] args) throws Throwable {
        ClassDesc owner = ClassDesc.of("MethodHandleDescLab$Target");
        DirectMethodHandleDesc staticDesc = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.STATIC, owner, "add",
                MethodTypeDesc.of(ConstantDescs.CD_int,
                        ConstantDescs.CD_int, ConstantDescs.CD_int));
        DirectMethodHandleDesc virtualDesc = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.VIRTUAL, owner, "decorate",
                MethodTypeDesc.of(ConstantDescs.CD_String, ConstantDescs.CD_String));
        DirectMethodHandleDesc constructorDesc =
                MethodHandleDesc.ofConstructor(owner, ConstantDescs.CD_int);
        DirectMethodHandleDesc fieldDesc = MethodHandleDesc.ofField(
                DirectMethodHandleDesc.Kind.GETTER,
                owner, "label", ConstantDescs.CD_String);
        DirectMethodHandleDesc staticFieldDesc = MethodHandleDesc.ofField(
                DirectMethodHandleDesc.Kind.STATIC_GETTER,
                owner, "shared", ConstantDescs.CD_int);

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle staticHandle = staticDesc.resolveConstantDesc(lookup);
        MethodHandle virtualHandle = virtualDesc.resolveConstantDesc(lookup);
        MethodHandle constructorHandle = constructorDesc.resolveConstantDesc(lookup);
        MethodHandle fieldHandle = fieldDesc.resolveConstantDesc(lookup);
        MethodHandle staticFieldHandle = staticFieldDesc.resolveConstantDesc(lookup);

        Target obj = (Target) constructorHandle.invokeExact(8);
        System.out.println("staticKind=" + staticDesc.kind());
        System.out.println("staticType=" + staticDesc.invocationType().descriptorString());
        System.out.println("virtualLookup=" + virtualDesc.lookupDescriptor());
        System.out.println("virtualType=" + virtualDesc.invocationType().descriptorString());
        System.out.println("constructorType=" + constructorDesc.invocationType().descriptorString());
        System.out.println("fieldType=" + fieldDesc.invocationType().descriptorString());
        System.out.println("staticFieldType=" + staticFieldDesc.invocationType().descriptorString());
        System.out.println("add=" + (int) staticHandle.invokeExact(3, 4));
        System.out.println("virtual=" + (String) virtualHandle.invokeExact(obj, "hi"));
        System.out.println("field=" + (String) fieldHandle.invokeExact(obj));
        System.out.println("shared=" + (int) staticFieldHandle.invokeExact());
    }
}
```

Biên dịch/chạy:

```sh
javac --release 21 -Xlint:all MethodHandleDescLab.java
java MethodHandleDescLab
```

**Stdout:**

```text
staticKind=STATIC
staticType=(II)I
virtualLookup=(Ljava/lang/String;)Ljava/lang/String;
virtualType=(LMethodHandleDescLab$Target;Ljava/lang/String;)Ljava/lang/String;
constructorType=(I)LMethodHandleDescLab$Target;
fieldType=(LMethodHandleDescLab$Target;)Ljava/lang/String;
staticFieldType=()I
add=7
virtual=[hi]
field=v8
shared=11
```

### 10.1. Cách đọc từng kiểu

- `STATIC`: `add(int,int)` là `(II)I` ở cả lookup và invocation; không có receiver.
- `VIRTUAL`: `lookupDescriptor()` cho `decorate(String)` là `(Ljava/lang/String;)Ljava/lang/String;`. `invocationType()` thêm một `Target` trước String argument.
- `CONSTRUCTOR`: `ofConstructor` chỉ nhận parameter types; invocation type trả `Target`.
- `GETTER`: instance field getter nhận receiver `Target` và trả `String`.
- `STATIC_GETTER`: static field getter không nhận receiver và trả `int`.
- Các lời gọi `invokeExact` dùng cast/gán return type đúng để call-site signature khớp. Việc resolve handle **không tự thực thi** member; lời gọi ở cuối chương trình mới thực hiện hành vi.

**Lưu ý:** code đặt trong default package để dễ chạy. Nếu dời vào package thật, binary name của nested `Target` thay đổi (ví dụ `com.acme.MethodHandleDescLab$Target`), nên phải điều chỉnh `ClassDesc.of(...)`. Đừng hard-code binary names trong thư viện tái sử dụng nếu có thể lấy từ class metadata đúng nguồn.

## 11. `MethodHandleDesc.asType` và lookup quyền truy cập

`MethodHandleDesc` có `asType(MethodTypeDesc targetType)`, tạo một **nominal description của handle sau adaptation** tương đương ý tưởng `MethodHandle.asType` ở runtime. Điều này **không** làm `MethodTypeDesc` của method khai báo thay đổi, và không bảo đảm mọi phép chuyển đổi đều hợp lệ.

Ví dụ:

```text
Method thực:       int twice(int)
Raw handle type:   (I)I
Adapted handle:    (B)J

caller gửi byte    -- widen --> int twice(int) -- widen return --> long
```

Đây là một adaptation hợp lệ: input `byte` widening thành `int`, kết quả `int` widening thành `long`. Ngược lại, adaptation đòi conversion không hợp lệ có thể thất bại ở bước resolve/adapt.

### 11.1. Access check là một bước riêng

Một `MethodHandleDesc` cho `private static int Vault.secret()` có thể tạo thành công, vì factory **không cần kiểm tra quyền của caller**. Nhưng khi resolve:

- `Lookup` **thiếu PRIVATE mode** không được phép liên kết private member nếu không thỏa access rules.
- `Lookup` có đủ nestmate/private privilege thì có thể thành công.
- `publicLookup()` không đồng nghĩa “một Lookup cùng loader nhưng không có quyền private”; trong một số tình huống nó còn không thấy application class thuộc unnamed module từ bootstrap-only search context. Vì vậy để thử **riêng quyền private** trong lab, dùng `dropLookupMode(PRIVATE)` trên lookup cùng class/loader rồi so với lookup đầy đủ.

Tránh dùng `setAccessible(true)` hoặc thêm `--add-opens` như một biện pháp chữa lỗi thiếu quyền mặc định. `Lookup` nên được cấp bởi đúng thành phần sở hữu capability đó, không được giả lập bằng text.

## 12. Lab 4 — bị từ chối quyền rồi resolve hợp lệ; adapter asType

Tạo file **`AccessAndAdaptLab.java`**:

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DirectMethodHandleDesc;
import java.lang.constant.MethodHandleDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

public class AccessAndAdaptLab {
    public static class Vault {
        private static int secret() {
            return 42;
        }
        public static int twice(int x) {
            return x * 2;
        }
    }

    public static void main(String[] args) throws Throwable {
        ClassDesc owner = ClassDesc.of("AccessAndAdaptLab$Vault");
        DirectMethodHandleDesc privateMethod = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.STATIC, owner, "secret",
                MethodTypeDesc.of(ConstantDescs.CD_int));
        System.out.println("privateNominal=" +
                privateMethod.invocationType().descriptorString());

        MethodHandles.Lookup restricted =
                MethodHandles.lookup().dropLookupMode(MethodHandles.Lookup.PRIVATE);
        try {
            privateMethod.resolveConstantDesc(restricted);
            System.out.println("restricted=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("restricted=IllegalAccessException");
        }

        MethodHandle accessible =
                privateMethod.resolveConstantDesc(MethodHandles.lookup());
        System.out.println("nestmate=" + (int) accessible.invokeExact());

        MethodHandleDesc raw = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.STATIC, owner, "twice",
                MethodTypeDesc.of(ConstantDescs.CD_int, ConstantDescs.CD_int));
        MethodTypeDesc desired =
                MethodTypeDesc.of(ConstantDescs.CD_long, ConstantDescs.CD_byte);
        MethodHandleDesc adapted = raw.asType(desired);
        MethodHandle adaptedHandle =
                adapted.resolveConstantDesc(MethodHandles.lookup());

        System.out.println("raw=" + raw.invocationType().descriptorString());
        System.out.println("adapted=" + adapted.invocationType().descriptorString());
        System.out.println("twice=" + (long) adaptedHandle.invokeExact((byte) 7));
        System.out.println("directDescribable=" +
                MethodHandles.lookup().findStatic(
                        Vault.class, "twice",
                        java.lang.invoke.MethodType.methodType(int.class, int.class))
                        .describeConstable().isPresent());
    }
}
```

```sh
javac --release 21 -Xlint:all AccessAndAdaptLab.java
java AccessAndAdaptLab
```

**Stdout:**

```text
privateNominal=()I
restricted=IllegalAccessException
nestmate=42
raw=(I)I
adapted=(B)J
twice=14
directDescribable=true
```

### 12.1. Phân biệt quyền và tính mô tả

- `privateMethod` vẫn tồn tại như một object danh nghĩa dù `restricted` không resolve được private member.
- `MethodHandles.lookup()` trong `AccessAndAdaptLab` có đủ quyền nestmate với nested `Vault` để resolve `secret` thành `MethodHandle` trả 42.
- `asType` chuyển nominal invocation type từ `(I)I` thành `(B)J`. Sau resolution, `invokeExact((byte)7)` nhận argument `byte` và return `long` bằng 14.
- `MethodHandle.describeConstable()` có thể trả một `Optional<MethodHandleDesc>` nếu method handle có mô tả danh nghĩa hợp lệ (ví dụ direct static method). Không mặc định mọi transformed/anonymous handle đều mô tả được.

**Chú ý thực tế:** các lỗi quyền `IllegalAccessException` khác các lỗi class không tồn tại (`ClassNotFoundException`) và các lỗi member không tồn tại. Đừng dùng một thông báo chung “descriptor invalid” khi factory đã tạo descriptor thành công.

## 13. Liên hệ với hằng động (CONSTANT_Dynamic)

Bốn kiểu trong tiêu đề là nền tảng mô tả hằng, nhưng **một dynamic constant thực sự** cần thêm metadata bootstrap. `DynamicConstantDesc<T>` là subtype của `ConstantDesc` biểu diễn một `CONSTANT_Dynamic_info` với:

- **Constant name**: tên danh nghĩa của hằng.
- **Constant type**: `ClassDesc` của kiểu kết quả.
- **Bootstrap method**: một `DirectMethodHandleDesc` trỏ tới bootstrap method.
- **Bootstrap arguments**: các static constant descriptors cần thiết khác, tùy bootstrap.
- **Resolution context**: `Lookup` và quy tắc tương ứng khi yêu cầu giải quyết.

JVM có `CONSTANT_Dynamic` cho loadable dynamic constants (`ldc` trên entry tương ứng) và `CONSTANT_InvokeDynamic` cho dynamic call sites. Chúng liên quan qua khái niệm bootstrap nhưng **không phải cùng constant pool tag**. `DynamicCallSiteDesc` thuộc `java.lang.constant` có nhiệm vụ danh nghĩa cho dynamic call sites; nó không phải thay thế `DynamicConstantDesc`.

### 13.1. Những phương thức bootstrap có sẵn

`ConstantDescs` cung cấp nhiều danh nghĩa của bootstrap handles có sẵn, ví dụ:

| ConstantDescs | Bootstrap tương ứng | Ý nghĩa điển hình |
| --- | --- | --- |
| `BSM_NULL_CONSTANT` | `ConstantBootstraps.nullConstant` | Hằng động nhận giá trị `null` cho reference type |
| `BSM_PRIMITIVE_CLASS` | `ConstantBootstraps.primitiveClass` | Hằng `Class<?>` của primitive |
| `BSM_ENUM_CONSTANT` | `ConstantBootstraps.enumConstant` | Lấy enum constant theo tên |
| `BSM_GET_STATIC_FINAL` | `ConstantBootstraps.getStaticFinal` | Đọc một static final field hợp lệ |
| `BSM_INVOKE` | `ConstantBootstraps.invoke` | Dùng bootstrap invocation để tạo giá trị |
| `BSM_VARHANDLE_FIELD` | `ConstantBootstraps.fieldVarHandle` | Mô tả hằng dynamic có giá trị VarHandle cho instance field |

Các `BSM_*` đều là descriptor cho bootstrap method, **không phải** kết quả bootstrap đã tính. Việc chọn bootstrap sai signature, không đủ quyền hoặc static args không hợp lệ có thể làm resolution thất bại. Đừng cho một dynamic constant tham chiếu bất kỳ handler do người dùng không tin cậy nhập mà không có chính sách xác thực.

### 13.2. Tạo descriptor không có nghĩa đã thêm CONSTANT_Dynamic vào class file

Code Java sau đây tạo một `DynamicConstantDesc` **trong heap** và dùng `resolveConstantDesc` để tính giá trị. Nó không biên dịch một `ldc CONSTANT_Dynamic` mới vào chính class file của chương trình. Muốn sinh bytecode có `CONSTANT_Dynamic_info`, cần một class-file generator phù hợp và lý giải bootstrap theo JVMS `4.4.10`, `5.4.3.6`.

Đây là khác biệt giữa **mô hình danh nghĩa của constant pool** và **class file đã được mã hóa**.

## 14. Lab 5 — DynamicConstantDesc và native ConstantDesc

Tạo file **`DynamicConstantLab.java`**:

```java
import java.lang.constant.ConstantDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DynamicConstantDesc;
import java.lang.invoke.MethodHandles;

public class DynamicConstantLab {
    public static void main(String[] args) throws ReflectiveOperationException {
        ConstantDesc text = "hello";
        ConstantDesc number = Integer.valueOf(7);
        DynamicConstantDesc<String> nominalNull = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_NULL_CONSTANT,
                "meaning",
                ConstantDescs.CD_String);

        System.out.println("stringSelf=" + text.resolveConstantDesc(MethodHandles.lookup()));
        System.out.println("integerSelf=" + number.resolveConstantDesc(MethodHandles.lookup()));
        System.out.println("dynamicSubtype=" + (nominalNull instanceof DynamicConstantDesc));
        System.out.println("dynamicName=" + nominalNull.constantName());
        System.out.println("dynamicType=" + nominalNull.constantType().descriptorString());
        System.out.println("dynamicResolvesNull=" +
                (nominalNull.resolveConstantDesc(MethodHandles.lookup()) == null));
        System.out.println("dynamicBootstrap=" +
                nominalNull.bootstrapMethod().methodName());
    }
}
```

```sh
javac --release 21 -Xlint:all DynamicConstantLab.java
java DynamicConstantLab
```

**Stdout:**

```text
stringSelf=hello
integerSelf=7
dynamicSubtype=true
dynamicName=meaning
dynamicType=Ljava/lang/String;
dynamicResolvesNull=true
dynamicBootstrap=nullConstant
```

### 14.1. Giải thích

- String và Integer thực thi `ConstantDesc` cho chính chúng, nên resolution trả giá trị tương ứng.
- `DynamicConstantDesc.ofNamed(BSM_NULL_CONSTANT,"meaning",CD_String)` tạo một nominal description của hằng `String` có giá trị `null`.
- `nominalNull.constantType()` là `CD_String` nên descriptor là `Ljava/lang/String;`.
- `nominalNull.resolveConstantDesc(lookup)` gọi đường bootstrap theo hợp đồng mô tả và nhận `null`; trong trường hợp này kết quả `== null` là true.
- `bootstrapMethod().methodName()` trả `nullConstant`, giúp thấy descriptor đang trỏ tới bootstrap nào. **Tên hằng** `meaning` khác với **tên bootstrap method** `nullConstant`.
- `ConstantDesc` và `DynamicConstantDesc` đều chỉ là các Java object được tạo, không thay đổi class file khi chạy lab.

**Ghi chú về null:** `null` không phải một `ConstantDesc` instance; ở đây một **descriptor object** tồn tại và nó *resolve tới* giá trị null. Nhầm hai điều này sẽ dẫn đến lỗi logic trong code dùng generic `ConstantDesc`.

## 15. `Constable` và mô tả ngược từ runtime values

`Constable` là giao diện cho object **có thể tự mô tả dưới dạng nominal constant descriptor**. Các API quan trọng:

| Runtime object | API | Loại Optional có thể nhận |
| --- | --- | --- |
| `String` | `describeConstable()` | `Optional<String>` |
| `Integer` | `describeConstable()` | `Optional<Integer>` |
| `Class<?>` | `Class.describeConstable()` | `Optional<ClassDesc>` |
| `MethodType` | `MethodType.describeConstable()` | `Optional<MethodTypeDesc>` |
| `MethodHandle` | `MethodHandle.describeConstable()` | `Optional<MethodHandleDesc>` |

`describeConstable()` **không bảo đảm luôn có giá trị**. Ví dụ một số class không thể được mô tả bằng tên danh nghĩa ổn định (hidden class); một số method handles tạo ra qua combinators/adapters có thể không biểu diễn được bằng descriptor hợp lệ. Hãy xử lý `Optional.empty()` như một kết quả có ý nghĩa, không `orElseThrow()` tràn lan trên dữ liệu chưa kiểm soát.

### 15.1. Khi nào dùng hướng xuôi, khi nào dùng hướng ngược?

**Hướng xuôi — nominal → runtime:**

```java
// Đoạn minh họa trong scope có quyền lookup.
ClassDesc desc = ClassDesc.of("java.lang.String");
Class<?> runtime = desc.resolveConstantDesc(MethodHandles.lookup());
```

Phù hợp khi nhận class-file metadata hoặc cấu hình symbolic, sau đó muốn link trong môi trường hiện tại.

**Hướng ngược — runtime → nominal:**

```java
// Đoạn minh họa với một Class<?> có thể mô tả.
java.util.Optional<ClassDesc> name = String.class.describeConstable();
```

Phù hợp khi muốn ghi lại mô tả danh nghĩa cho tooling. Đừng mặc nhiên coi phép đi rồi về bảo toàn **class loader identity**; nominal descriptors không lưu defining loader và cần một Lookup đúng khi resolve lại.

### 15.2. Tên lớp và descriptor equality không đủ thay access policy

Một `ClassDesc` có thể bằng nhau giữa hai plugin, còn `Class<?>` runtime khác nhau. Một `MethodHandleDesc` có tên owner/name/descriptor giống nhau cũng có thể resolve tới member khác hoặc không resolve được khi đổi Lookup. Vì thế `equals` của nominal descriptors phục vụ **so cấu trúc mô tả** — không phải xác thực capability đã cấp.

## 16. Resolution pipeline, lỗi và kiểm tra an toàn

Một tiến trình tiêu chuẩn khi dùng descriptors trong runtime:

```text
[1] Nhận metadata từ class file/config nguồn đáng tin
     |
[2] Tạo ClassDesc / MethodTypeDesc / MethodHandleDesc
     |   validate syntax và descriptor kind
     v
[3] Xác định class loader, module layer, Lookup context hợp lệ
     |
[4] resolveConstantDesc(lookup)
     |   resolve class + access + member lookup/linking + bootstrap nếu có
     v
[5] Kiểm tra runtime MethodType / MethodHandle type và capability
     |
[6] Invoke với chữ ký đúng hoặc truyền value cho consumer
     |
[7] Ghi nhận lỗi theo pha, quản lý cache/lifecycle
```

**Nhóm lỗi:**

| Hiện tượng | Pha và nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `IllegalArgumentException` ở `ClassDesc.ofDescriptor` | Field descriptor sai grammar, ví dụ tên object không có `;` | Dùng đúng JVMS `4.3.2`; không nhập method descriptor. |
| `IllegalArgumentException` ở `MethodTypeDesc.ofDescriptor` | Method descriptor sai grammar, ví dụ `(V)I` | `V` chỉ hợp lệ ở return; kiểm tra dấu ngoặc, thứ tự kiểu. |
| `ClassNotFoundException` khi resolve `ClassDesc` | Tên hợp lệ nhưng lookup loader không tìm được class | Xem binary name, classpath/module path và lookup class loader. |
| `IllegalAccessException` khi resolve handle | Lookup không có quyền access class/member/module | Dùng Lookup hợp pháp từ đúng owner/module, không tùy tiện mở quyền. |
| `NoSuchMethodException` / `NoSuchFieldException` | Member name/kind/type không khớp runtime owner | So bytecode descriptor bằng `javap -s` và kiểm tra erased types. |
| `LinkageError` | Resolution/linkage không thể hoàn tất | Kiểm tra dependencies, class version, loaders, module graph. |
| `WrongMethodTypeException` khi invoke | Call-site signature không phù hợp `MethodHandle.type()` | In `type()`, kiểm tra receiver/return cast, adapt có chủ đích. |
| `ClassCastException` | Caller đưa object reference không đúng runtime type | Xem class identity, loader, type conversions. |
| `Optional.empty()` từ `describeConstable()` | Runtime entity không có nominal description hợp lệ | Thiết kế fallback, không khẳng định mọi object serialize được. |
| Dynamic constant bootstrap thất bại | Bootstrap/name/type/static arguments không phù hợp | Kiểm tra bootstrap signature, lookup quyền và error cause. |

**Chú ý lỗi resolve:** API `ConstantDesc.resolveConstantDesc` khai báo `ReflectiveOperationException`, nhưng những lỗi `LinkageError` hoặc runtime exceptions vẫn có thể phát sinh tùy ngữ cảnh. Không catch `Exception` rồi bỏ qua nguyên nhân hoặc biến lỗi quyền thành lỗi cú pháp.

### 16.1. Class loader là phần bắt buộc của ngữ cảnh

Một nominal descriptor chỉ giữ tên lớp. Nếu hệ thống plugin có nhiều class loaders:

- Không dùng `ClassDesc.of("com.acme.Message")` rồi resolve bằng Lookup của core khi thực sự cần class của plugin.
- Không viết cache key runtime chỉ là chuỗi `"Lcom/acme/Message;"`.
- Không chia sẻ `MethodHandle` chứa runtime `Class<?>` của plugin A để gọi instance được loader B định nghĩa chỉ vì tên class giống.
- Quyết định một shared API/SPI loader hoặc lookup policy rõ ràng, sau đó dùng `resolveConstantDesc` theo quy tắc đó.

**Resolution có thể là hành động quan sát được**, kéo theo class loading và đôi khi linking/initialization theo member/bootstrap liên quan. Đừng chạy resolution đối với danh sách member/owner names do người dùng không tin cậy cung cấp mà không lọc và giới hạn tài nguyên.

## 17. Từ constant descriptors đến class file

Mặc dù các lab dùng Java reflection, lớp API này đặc biệt hữu ích khi xây công cụ đọc/ghi bytecode.

| Constant-pool structure | Thông tin biểu diễn | Java nominal API tương ứng |
| --- | --- | --- |
| `CONSTANT_Class_info` | Class/interface/array symbolic type | `ClassDesc` |
| `CONSTANT_MethodType_info` | Method descriptor string | `MethodTypeDesc` |
| `CONSTANT_MethodHandle_info` | Reference kind và member reference | `DirectMethodHandleDesc` |
| `CONSTANT_Dynamic_info` | Bootstrap, name, return type, static args | `DynamicConstantDesc` |
| `CONSTANT_InvokeDynamic_info` | Bootstrap/linkage của dynamic call site | `DynamicCallSiteDesc` |
| `CONSTANT_String_info` | String literal | `String` (native `ConstantDesc`) |
| Integer/Long/Float/Double entries | Numeric constants | Boxed numeric `ConstantDesc` tương ứng |

**Không diễn dịch bảng là class-file tag có Java object runtime tương ứng một-một**. Trong class file còn indices, name-and-type structures và bootstrap-method table; một bytecode writer phải ánh xạ đúng các liên kết đó. `ConstantDesc` là interface của symbolic recipe chứ không phải class-file parser.

### 17.1. Kiểm tra bytecode đã biên dịch

Sau khi build `MethodHandleDescLab.java`:

```sh
javap -v -p MethodHandleDescLab
javap -s -p MethodHandleDescLab
```

- `-v` hiện constant pool và một số metadata class file.
- `-s` hiện method/field descriptors theo JVM; trong Lab 3, `add` có descriptor `(II)I`, `decorate` có `(Ljava/lang/String;)Ljava/lang/String;`.
- Những nominal descriptors mà chương trình **tạo bằng factory ở runtime** không nhất thiết xuất hiện trực tiếp như các `CONSTANT_MethodHandle_info` entries tương ứng trong class file của chính chương trình.
- Đừng khẳng định Java compiler tự phát sinh `CONSTANT_Dynamic` chỉ vì code có `DynamicConstantDesc.ofNamed(...)`. Đó là **factory call**, không phải một chỉ thị compiler tạo dynamic constant pool entry.

### 17.2. Trường hợp method type không representable ở runtime

`MethodTypeDesc` có thể chứa method descriptor hợp lệ về cấu trúc với **quá nhiều parameter slots** cho `MethodType`, trong khi một phương thức JVM thực tế bị giới hạn bởi quy tắc slots. Nếu viết bytecode emitter, phải kiểm tra **ràng buộc JVM** trước khi serialize thành class file và tách riêng các lỗi parser vs runtime. Tránh giả định “tạo nominal object thành công” là validator class file hoàn chỉnh.

## 18. Các lỗi tư duy thường gặp

| Hiểu nhầm | Sự thật |
| --- | --- |
| “`ClassDesc.of` tạo class runtime” | Factory chỉ tạo symbolic description; `resolveConstantDesc` mới cố resolve. |
| “`ClassDesc` là `Class<?>` thu nhỏ” | Một cái chứa danh nghĩa, một cái chứa runtime identity gắn loader. |
| “`MethodTypeDesc` giữ `List<String>`” | Method type descriptors chỉ giữ erased JVM types; generic signature là metadata khác. |
| “`MethodHandleDesc.ofMethod` đã chứng minh method tồn tại” | Factory có thể thành công dù owner/member chưa tồn tại. |
| “`ofMethod(VIRTUAL)` phải nhận kiểu có receiver” | Lookup method type không chứa receiver; `invocationType()` mới chứa receiver. |
| “Constructor description trả `void`” | `<init>` JVM trả void, nhưng constructor **handle invocation** trả instance mới. |
| “Field dùng `MethodTypeDesc` làm type đầu vào factory” | `ofField` nhận `ClassDesc fieldType`; invocation type được suy theo kind. |
| “`asType` là phép cast value ngay lập tức” | Tạo adapted nominal handle; resolve rồi invoke mới có chuyển đổi runtime. |
| “Có cùng descriptor là cùng method handle runtime” | Lookup class/loader/module/quyền và owner identity có thể khác. |
| “`publicLookup()` luôn là lookup thích hợp cho mọi application class” | Ngữ cảnh tìm class của public lookup có giới hạn, đôi khi lỗi trước access check. |
| “`describeConstable()` luôn có giá trị” | Trả Optional, có thể empty cho runtime value không có nominal representation. |
| “`DynamicConstantDesc` chính là một giá trị đã chạy bootstrap” | Nó là recipe; `resolveConstantDesc` mới yêu cầu bootstrap. |
| “Gọi factory tự chèn `CONSTANT_Dynamic` vào class file” | Class-file generation là công việc khác. |
| “`equals` của descriptor xác nhận an toàn” | Equals chỉ so symbolic description, không thay authorization. |
| “Mọi `resolveConstantDesc` đều cache cùng instance” | Contract không bảo đảm caching per descriptor object. |

**Kinh nghiệm thiết kế:** lựa chọn giữa nominal/runtime theo giai đoạn. Phần tooling có thể giữ nominal descriptors, còn phần thực thi cần resolve có kiểm soát. Đừng tự viết parser chỉ bằng tách dấu chấm/dấu phẩy khi JDK đã có factory cho grammar.

## 19. Bài tập và đáp án định hướng

**Bài 1 — Tạo ClassDesc.** Viết danh nghĩa cho `int`, `String[]`, `java.util.Map.Entry`, `long[][]`. Đáp án descriptor lần lượt: `I`, `[Ljava/lang/String;`, `Ljava/util/Map$Entry;`, `[[J`. Giải thích vì sao nested class dùng `$` thay vì chuyển dấu chấm của source class name vào internal name.

**Bài 2 — Phân biệt danh nghĩa và runtime.** Dùng `ClassDesc.of("com.example.NotThere")` rồi `descriptorString()` trước `resolveConstantDesc`. Tại sao bước đầu được nhưng bước sau thất bại? Viết phân loại lỗi không lạm dụng `IllegalArgumentException`.

**Bài 3 — MethodTypeDesc factory.** Xây description cho `String combine(int, String[])` bằng `MethodTypeDesc.of`, tự dự đoán `(I[Ljava/lang/String;)Ljava/lang/String;`. Sau đó thêm một `long` vào index 1 và đổi return thành `void`. Xác minh từ `descriptorString()`.

**Bài 4 — Grammar.** Phân biệt `(V)I`, `(I)V` và `[I`. Chỉ `(I)V` là method descriptor hợp lệ; `[I` là field descriptor của `int[]`, không có dấu ngoặc method. `(V)I` sai vì tham số không thể `void`.

**Bài 5 — Virtual receiver.** Từ Lab 3, tính `virtualDesc.lookupDescriptor()` và `virtualDesc.invocationType()`. Tại sao `lookupDescriptor` chỉ có `String` parameter nhưng `invokeExact` phải truyền `Target`?

**Bài 6 — Constructor.** Thêm `Target(String,int)`, xây `MethodHandleDesc.ofConstructor(owner,CD_String,CD_int)`. Giải thích `<init>` trong class file có return `V` còn `invocationType` trả `Target`.

**Bài 7 — Field.** Thêm `public long count` trong `Target`. Dự đoán invocation type cho `Kind.GETTER` và `Kind.SETTER`. Đáp án: `(LMethodHandleDescLab$Target;)J` và `(LMethodHandleDescLab$Target;J)V`.

**Bài 8 — Access modes.** Trong Lab 4, so `restricted` với `MethodHandles.lookup()`, rồi đổi method `Vault.secret` từ private thành public. Phân biệt ảnh hưởng của access modifier với class loader. Chỉ chạy thử trên class/Lookup mà bạn sở hữu.

**Bài 9 — asType.** Thay adapter `(B)J` bằng `(S)J` cho input `short`. Lý giải widening `short → int` và `int → long`. Không mặc định phép `String → int` có thể chuyển đổi.

**Bài 10 — Dynamic constant.** Dùng `DynamicConstantDesc.ofNamed(BSM_NULL_CONSTANT,"empty",CD_String)`. Đọc `constantName()`, `constantType()` và `bootstrapMethod()`. Tại sao descriptor object **không null** dù resolve trả `null`?

**Bài 11 — Loader identity.** Tưởng tượng hai module plugin có cùng binary name `plugin.api.Task` nhưng class loader khác. Cho một `ClassDesc.of("plugin.api.Task")`, dự đoán `equals` của hai descriptions và phân biệt `Class<?>` sau resolution bằng Lookup A/B. Nêu cách cache đúng.

**Bài 12 — Constable Optional.** Từ các runtime objects `String.class`, `MethodType.methodType(int.class,int.class)` và `MethodHandles.lookup().findStatic(...)`, gọi `describeConstable()`. Kiểm tra Optional trước khi dùng; tại sao không thể mặc định Optional luôn non-empty trong ứng dụng generic?

**Bài 13 — Bytecode verification.** Dùng `javap -v` kiểm tra class file của một lab. Phân biệt constant pool entry thực trong file với một `ConstantDesc` được Java code tạo trong heap. Không suy rằng mọi dynamic description đều trở thành `CONSTANT_Dynamic`.

### 19.1. Checklist kết thúc

- [ ] Giải thích được “recipe, không phải runtime value”.
- [ ] Tạo/đọc `ClassDesc` primitive, object, array, nested class đúng grammar.
- [ ] Tạo/đọc `MethodTypeDesc` với đúng return/parameter order và phân biệt readable display.
- [ ] Phân biệt `MethodHandleDesc.lookupDescriptor` với `invocationType` cho STATIC/VIRTUAL/CONSTRUCTOR/FIELD.
- [ ] Resolve với `Lookup` hợp pháp; gọi `MethodHandle.invokeExact` với signature chuẩn.
- [ ] Nêu được lỗi grammar, missing class, access denied và runtime conversion là các pha khác nhau.
- [ ] Phân biệt `DynamicConstantDesc` và constant pool `CONSTANT_Dynamic` với `DynamicCallSiteDesc`.
- [ ] Không hard-code loader identity, không dựa vào `==` cho descriptor objects và không assume mọi `Constable` có nominal description.
- [ ] Chạy và hiểu đúng stdout của cả năm lab.

## 20. Tài liệu chuẩn Java SE 21 và JVM

- [Java SE 21 — java.lang.constant package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/package-summary.html): khái niệm nominal descriptors, constant pool và resolution.
- [Java SE 21 — ConstantDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/ConstantDesc.html): sealed interface, `resolveConstantDesc`, không cache theo contract.
- [Java SE 21 — ClassDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/ClassDesc.html): name factories, arrays, type descriptors, display và resolution.
- [Java SE 21 — MethodTypeDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/MethodTypeDesc.html): method description, editing và runtime resolution.
- [Java SE 21 — MethodHandleDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/MethodHandleDesc.html): static/virtual/field/constructor factories, adapter, invocationType.
- [Java SE 21 — DirectMethodHandleDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/DirectMethodHandleDesc.html) và [Kind](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/DirectMethodHandleDesc.Kind.html): member kind, owner, method name và lookup descriptor.
- [Java SE 21 — ConstantDescs](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/ConstantDescs.html): predefined `CD_*` và `BSM_*`.
- [Java SE 21 — DynamicConstantDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/DynamicConstantDesc.html): bootstrap name/type/args.
- [Java SE 21 — Constable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/Constable.html): `describeConstable` và Optional.
- [JVMS 21 `4.3 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3): field/method grammar.
- [JVMS 21 `4.4 — Constant Pool](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4): constant pool tags và symbolic references.
- [JVMS 21 `5.4.3 — Resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3): từ symbolic information đến runtime entities.
- [Java SE 21 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): resolution và quyền truy cập.
- [JDK 21 — javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): kiểm tra descriptors trong class file.

**Thông điệp chính:** `ClassDesc` mô tả **lớp theo tên**, `MethodTypeDesc` mô tả **chữ ký phương thức theo tên**, `MethodHandleDesc` mô tả **hành động liên kết member theo owner/name/kind/type**, và `ConstantDesc` là hợp đồng chung để **resolve chúng dưới một Lookup cụ thể**. Khi hằng có bootstrap, `DynamicConstantDesc` bổ sung phần recipe đó. Hãy giữ symbolic metadata tách khỏi runtime authority và chỉ resolve khi đã có loader/module/Lookup hợp lệ.
