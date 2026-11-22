# Không suy ra toàn bộ cú pháp nguồn từ cờ trong class file

## 1. Vấn đề cần hiểu

Khi dùng Java Reflection, bạn có thể gọi `Class.getModifiers()`, `Field.getModifiers()`, `Method.getModifiers()` hoặc `Constructor.getModifiers()`, rồi kiểm tra bằng `java.lang.reflect.Modifier`. Khi đọc tệp `.class` qua `javap -v`, bạn cũng nhìn thấy các giá trị `access_flags`, chẳng hạn `ACC_PUBLIC`, `ACC_FINAL`, `ACC_STATIC`, `ACC_ABSTRACT`.

Tuy nhiên, **modifier và flag chỉ mô tả một phần đặc tính của chương trình đã biên dịch; chúng không phải bản chụp nguyên văn mã nguồn Java**. Không thể chỉ dựa vào các cờ này để dựng lại đầy đủ câu lệnh khai báo, biểu thức, cách viết tham số, từ khóa xuất hiện tường minh hay toàn bộ cú pháp nguồn ban đầu.

Ví dụ, hai khai báo sau có thể dẫn đến cùng những modifier hiệu lực cho phương thức:

```java
interface First {
    void run();                 // public abstract được ngầm hiểu
}

interface Second {
    public abstract void run(); // Viết tường minh hai modifier
}
```

Trong Reflection, `getDeclaredMethod("run").getModifiers()` ở cả hai trường hợp đều mang `public` và `abstract`. Từ kết quả ấy không thể biết tác giả đã viết tường minh `public abstract` hay để trình biên dịch suy ra theo quy tắc ngôn ngữ.

**Phạm vi bài này:** cách đọc và giới hạn diễn giải modifier/flag của *lớp, trường, phương thức, constructor và tham số* trong bối cảnh Java Reflection và class file; phân biệt dữ liệu thật sự có thể quan sát với cú pháp nguồn không được lưu giữ.

## 2. Quá trình biên dịch làm mất thông tin cú pháp như thế nào?

```text
Mã nguồn .java
  ├── từ khóa modifier, kiểu, tham số, chú thích
  ├── biểu thức, câu lệnh, import, định dạng, tên biến cục bộ
  └── đường đi cú pháp: khai báo tường minh / ngầm định
             │ javac / compiler / bytecode transformation
             ▼
Tệp .class
  ├── constant pool và access_flags
  ├── mô tả kiểu JVM (descriptors)
  ├── field_info, method_info, bytecode
  └── attributes: Signature, Exceptions, InnerClasses, ...
             │ Reflection / javap / class-file reader
             ▼
Thông tin cấu trúc + hành vi đã biên dịch
             ≠
Bản gốc đầy đủ của cú pháp .java
```

Một tệp `.class` lưu những gì JVM cần để nạp, xác minh và chạy mã, cùng các metadata mà trình biên dịch hoặc công cụ tạo bytecode chọn ghi thêm. Đây là **biểu diễn đã được chuyển đổi**, không phải cây cú pháp nguồn Java có thể đảo ngược hoàn toàn.

Những khác biệt phải phân biệt:

- **Nguồn:** có thể có cú pháp khác nhau nhưng cùng ý nghĩa và cùng modifier hiệu lực, ví dụ `void run();` và `public abstract void run();` trong interface.
- **Class file:** có nhiều vùng thông tin. `access_flags` chỉ là tập bit; descriptors, bytecode và các attributes mang các loại thông tin riêng biệt.
- **Reflection:** là API mức cao diễn giải cấu trúc đã nạp. Kết quả `getModifiers()` không tương ứng một-một với danh sách từ khóa từng xuất hiện trong nguồn; một số chi tiết khác cần API riêng.
- **Compiler / bytecode tools:** có thể bổ sung hoặc biến đổi cấu trúc, như tạo phương thức `bridge` và các phần tử `synthetic`. Không thể mặc định mọi phần tử quan sát được đều có một khai báo tường minh trong mã nguồn.

Từ một số thuộc tính, ta có thể **suy ra hợp lệ về kiểu thành viên ở runtime**. Nhưng suy luận đó khác với khẳng định tác giả đã viết chính xác chuỗi token nào trong tệp `.java`.

## 3. `access_flags` mô tả điều gì, và ở đâu?

Theo định dạng class file của JVM, nhiều cấu trúc có trường `access_flags`: phần định nghĩa class/interface, mỗi `field_info`, mỗi `method_info`; riêng metadata khác có thể chứa các tập flag riêng. **Cùng một vị trí bit có thể mang ý nghĩa khác nhau tùy cấu trúc.**

| Vị trí | Ví dụ cờ | Thông tin được mô tả |
| --- | --- | --- |
| Class/interface header | `ACC_PUBLIC`, `ACC_FINAL`, `ACC_INTERFACE`, `ACC_ABSTRACT`, `ACC_ANNOTATION`, `ACC_ENUM`, `ACC_MODULE` | Đặc tính của kiểu trong class file |
| `field_info` | `ACC_PUBLIC`, `ACC_PRIVATE`, `ACC_STATIC`, `ACC_FINAL`, `ACC_VOLATILE`, `ACC_TRANSIENT`, `ACC_SYNTHETIC`, `ACC_ENUM` | Khả năng truy cập và tính chất của field |
| `method_info` | `ACC_PUBLIC`, `ACC_PRIVATE`, `ACC_STATIC`, `ACC_FINAL`, `ACC_SYNCHRONIZED`, `ACC_BRIDGE`, `ACC_VARARGS`, `ACC_NATIVE`, `ACC_ABSTRACT`, `ACC_SYNTHETIC` | Tính chất phương thức ở JVM |
| `InnerClasses` attribute | Các cờ dành cho thông tin lớp lồng, gồm `ACC_STATIC` | Metadata về lớp thành viên/lớp lồng trong quan hệ bao chứa |
| `MethodParameters` attribute | `ACC_FINAL`, `ACC_SYNTHETIC`, `ACC_MANDATED` | Metadata của *tham số*, nếu attribute này hiện diện |

**Lưu ý về bảng:** đây là các ví dụ, không phải danh sách đầy đủ cho mọi phiên bản JVM. Không hoán đổi bảng cờ giữa các loại cấu trúc. Ví dụ, `ACC_STATIC` có thể xuất hiện ở field hoặc method, còn thông tin một *lớp thành viên* là `static` được mô tả thông qua `InnerClasses`, chứ không phải một bit `ACC_STATIC` trong class header.

Những cờ như `ACC_SUPER` mang ý nghĩa liên quan tới cách JVM xử lý class file; chúng **không phải từ khóa modifier trong khai báo Java**. Ngược lại, không phải mọi từ khóa hoặc đặc điểm Java đều có một bit tương ứng trong `access_flags`.

### 3.1. Phân biệt flag của class file với `Modifier` của Reflection

`java.lang.reflect.Modifier` cung cấp các phép kiểm tra như:

```java
Modifier.isPublic(mods)
Modifier.isPrivate(mods)
Modifier.isProtected(mods)
Modifier.isStatic(mods)
Modifier.isFinal(mods)
Modifier.isAbstract(mods)
Modifier.isSynchronized(mods)
Modifier.isTransient(mods)
Modifier.isVolatile(mods)
Modifier.isNative(mods)
Modifier.isInterface(mods)
Modifier.toString(mods)
```

`mods` là số nguyên trả về từ API `getModifiers()` tương ứng. `Modifier.toString(mods)` hiển thị những modifier mà API đó nhận diện theo một thứ tự biểu diễn chuẩn; nó **không** bảo đảm tái tạo thứ tự hoặc sự hiện diện tường minh của từ khóa trong mã nguồn.

Không lấy một số nguyên `access_flags` tùy ý từ tệp `.class` rồi coi nó hoàn toàn tương đương với `getModifiers()`. Lý do gồm: phạm vi flag khác nhau giữa class/field/method, các bit có ý nghĩa riêng của JVM, và việc Reflection có thể sử dụng metadata khác để mô tả kiểu. Chẳng hạn, với lớp thành viên `static`, `Class.getModifiers()` có thể báo `static` dựa trên thông tin lớp lồng.

### 3.2. Modifier không phải tất cả metadata

Vẫn có những chi tiết quan sát được qua các API chuyên biệt:

| Cần kiểm tra | API hoặc metadata phù hợp | Vì sao `getModifiers()` chưa đủ |
| --- | --- | --- |
| Phương thức varargs | `Method.isVarArgs()` / `ACC_VARARGS` | `varargs` không có phép thử `Modifier.isVarArgs` |
| Phương thức bridge | `Method.isBridge()` / `ACC_BRIDGE` | Bridge có thể do compiler sinh ra |
| Phần tử synthetic | `isSynthetic()` / `ACC_SYNTHETIC` | Không tương đương một từ khóa khai báo Java |
| Phương thức `default` trong interface | `Method.isDefault()` | Không có `Modifier.isDefault` |
| Class là record | `Class.isRecord()`, `getRecordComponents()`, `Record` attribute | `record` không được phục hồi chỉ từ `getModifiers()` |
| Class là sealed | `Class.isSealed()`, `getPermittedSubclasses()`, `PermittedSubclasses` attribute | Danh sách lớp được phép kế thừa nằm ngoài tập modifier cơ bản |
| Kiểu generic | `getGenericType()` / `getGenericReturnType()`; `Signature` attribute nếu có | JVM descriptor chủ yếu ghi kiểu đã xóa, không phản ánh đầy đủ generics |
| Annotation | API annotation và annotation attributes phù hợp với retention | Không phải cờ access |
| Tên tham số | `Parameter.getName()` và `isNamePresent()`; `MethodParameters` nếu có | Tên tham số không nằm trong `access_flags` |

Các thông tin bổ sung này vẫn **không biến class file thành mã nguồn đầy đủ**. Ví dụ, `Signature` có thể giúp tìm kiểu generic khai báo nhưng không phục hồi cách sắp dòng hoặc tên import; `Record` mô tả thành phần record nhưng không tái tạo chính xác mọi biểu thức ban đầu.

## 4. Ví dụ runnable: cùng ý nghĩa, cú pháp nguồn khác nhau

Chương trình sau dùng Java 17 trở lên để minh họa ba giới hạn: modifier ngầm định trong interface, kiểu tham số varargs và cách Reflection tách modifier khỏi những thuộc tính khác.

Tạo tệp `FlagSourceDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

interface Action {
    void execute(); // public abstract ngầm định
}

public class FlagSourceDemo {
    private final int counter = 7;

    public void print(String... values) {
    }

    public void printArray(String[] values) {
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method action = Action.class.getDeclaredMethod("execute");
        Field field = FlagSourceDemo.class.getDeclaredField("counter");
        Method varargs = FlagSourceDemo.class
                .getDeclaredMethod("print", String[].class);
        Method ordinaryArray = FlagSourceDemo.class
                .getDeclaredMethod("printArray", String[].class);

        System.out.println("interface method: "
                + Modifier.toString(action.getModifiers()));
        System.out.println("field: "
                + Modifier.toString(field.getModifiers()));
        System.out.println("varargs parameter: "
                + varargs.getParameterTypes()[0].getTypeName());
        System.out.println("print is varargs: " + varargs.isVarArgs());
        System.out.println("printArray is varargs: "
                + ordinaryArray.isVarArgs());
        System.out.println("class is public: "
                + Modifier.isPublic(FlagSourceDemo.class.getModifiers()));
    }
}
```

Biên dịch và chạy:

```bash
javac FlagSourceDemo.java
java FlagSourceDemo
```

Stdout:

```text
interface method: public abstract
field: private final
varargs parameter: java.lang.String[]
print is varargs: true
printArray is varargs: false
class is public: true
```

Cách đọc:

1. Trong mã nguồn, `Action.execute()` **không viết** `public abstract`. Nhưng hai thuộc tính đó là ngầm định theo quy tắc interface; khi xem phương thức đã biên dịch, Reflection trả về `public abstract`. Vì vậy, `Modifier.toString` không chứng minh đây là các từ khóa tác giả đã gõ.
2. `counter` thật sự được khai báo `private final`, nên Reflection báo `private final`. Nhưng từ hai cờ ấy không suy ra biểu thức khởi tạo `7`, vị trí trong tệp hay khoảng trắng/cách viết khác của field.
3. `print(String... values)` có dạng tham số nguồn `...`; `printArray(String[] values)` dùng `[]`. Reflection thấy kiểu tham số trực tiếp của cả hai là `String[]`. Phải hỏi `isVarArgs()` mới thấy khác biệt metadata varargs.
4. `Class.isPublic` (qua `Modifier.isPublic`) trả về thuộc tính hiệu lực của lớp. Nó không cho biết toàn bộ body, danh sách import hoặc cách triển khai.

### 4.1. Đối chiếu bằng `javap`

Từ thư mục có các tệp `.class` vừa biên dịch, chạy:

```bash
javap -p FlagSourceDemo
javap -v -p FlagSourceDemo
javap -v -p Action
```

Trong bản `javap -v -p FlagSourceDemo`, hãy tìm `print` và `printArray`:

- Cả hai có **descriptor JVM** `([Ljava/lang/String;)V`, nghĩa là một tham số là mảng `String[]` và trả về `void`.
- `print` có `ACC_VARARGS` trong flag của phương thức.
- `printArray` không có `ACC_VARARGS`.
- `javap -p` có thể trình bày chữ ký ở dạng gần mã Java để dễ đọc, nhưng đây là bản **diễn giải lại từ class file**, không phải bằng chứng về toàn bộ biểu thức, cú pháp hay định dạng nguồn ban đầu.

Trong `Action.class`, phương thức `execute` được biểu diễn là `public abstract` dù khai báo Java chỉ viết `void execute();`. Các modifier hiệu lực và các token thực tế trong source là hai câu hỏi khác nhau.

`javap -v` cũng liệt kê nhiều thuộc tính và thông tin JVM khác. Không nên lấy riêng `flags: ...` để suy luận ra toàn bộ khai báo nguồn, cũng không nên xem đầu ra `javap` là bản Java có thể dựng lại chính xác nguyên văn.

## 5. Các trường hợp dễ suy diễn sai

### 5.1. Modifier ngầm định, từ khóa thừa về nghĩa và cách viết tương đương

Trong interface, các field ngầm định là `public static final`; phương thức thông thường không có body và không đánh dấu `private`, `static` hay `default` sẽ là `public abstract`. Trong interface lồng nhau hoặc khai báo nested phù hợp cũng có các quy tắc ngầm định về `static`. Reflection quan sát **thuộc tính hiệu lực**, không chỉ modifier được ghi ra.

```java
interface Settings {
    int LIMIT = 10; // ngầm định public static final
}
```

Dù tác giả viết `int LIMIT` hay `public static final int LIMIT`, field trong class file có cùng các modifier liên quan. Không dùng `Modifier.toString(field.getModifiers())` để phân biệt hai cách viết.

**Cảnh báo:** quy tắc ngầm định thay đổi theo loại khai báo (class, interface, enum, record, annotation type, field, method...). Không mặc định mọi thành viên thiếu từ khóa đều có cùng quyền truy cập.

### 5.2. `varargs` không tương đương chỉ nhìn `String[]`

`String...` ở vị trí tham số cuối của phương thức có **kiểu mảng** ở JVM. Do đó, chỉ đọc `getParameterTypes()` hoặc descriptor không phân biệt được nó với một tham số `String[]` thông thường. `ACC_VARARGS` và `Method.isVarArgs()` cho biết một thuộc tính runtime bổ sung.

Ngay cả khi metadata varargs hiện diện, điều đó chỉ giúp xác định phương thức **được đánh dấu varargs trong class file**. Một class file có thể được sinh hoặc chỉnh sửa bởi công cụ không phải `javac`; không được khẳng định bạn đã tìm lại được chính xác token hay toàn bộ định dạng nguồn của tác giả.

### 5.3. Generic types và type erasure

Trong Java:

```java
java.util.List<String> names;
java.util.List<Integer> ages;
```

Các field có **descriptor kiểu thô `java.util.List`** do type erasure. Trình biên dịch Java thường ghi thêm `Signature` attribute để giữ thông tin generic mà Reflection dùng với `Field.getGenericType()`. Nếu metadata này thiếu hoặc bị loại bỏ, class file không đủ để khôi phục tham số kiểu gốc chỉ từ descriptor và flags.

Ngay cả khi đọc được `List<String>` qua `Signature`, bạn vẫn không thể xác định chắc chắn tác giả dùng `import java.util.List;` rồi viết `List<String>`, hay viết đầy đủ `java.util.List<String>`.

Cùng nguyên tắc áp dụng cho cú pháp generic method, wildcard và nhiều chi tiết của khai báo kiểu.

### 5.4. Local variable, tên tham số và dấu vết debug

Tên biến cục bộ, line numbers hoặc tên tham số không nằm trong modifier của method. Một số thông tin có thể được ghi vào `LocalVariableTable`, `LineNumberTable` hoặc `MethodParameters` tùy cấu hình biên dịch.

Dùng `javac -parameters` khi muốn lưu tên tham số nguồn theo cơ chế `MethodParameters` phổ biến với `javac`. Có thể kiểm tra `Parameter.isNamePresent()`. Nếu không có tên thật, `Parameter.getName()` có thể trả tên tổng hợp như `arg0`. Việc thiếu metadata **không có nghĩa mã nguồn không có tên tham số**.

Tương tự, `javac -g` có thể tạo metadata debug; nó không lưu đầy đủ mọi token, chú thích và biểu thức nguồn. Với tối ưu hóa hoặc bytecode transformation, quan hệ giữa bytecode và từng dòng nguồn có thể càng khó tái dựng.

### 5.5. Compiler-generated, synthetic và bridge methods

Khi generics hoặc các đặc điểm ngôn ngữ cần bảo đảm tương thích lời gọi ở JVM, compiler có thể sinh thêm method `bridge`. Nó có thể xuất hiện trong `getDeclaredMethods()` dù lập trình viên không khai báo trực tiếp một method riêng tương ứng trong source.

```java
class Parent<T> {
    T value() {
        return null;
    }
}

class Child extends Parent<String> {
    @Override
    String value() {
        return "ok";
    }
}
```

Ở cơ chế biên dịch Java điển hình, `Child` có thể có một method sinh ra để nối chữ ký erased của `Parent.value()` với `Child.value()`. Kiểm tra `Method.isBridge()` và `Method.isSynthetic()` thay vì suy ra rằng mọi `Method` có một khai báo viết tay. Bridge/synthetic là những thuộc tính cấu trúc, không phải các từ khóa bắt buộc tồn tại ở nguồn.

Lưu ý: không tự áp dụng các quy tắc suy luận về nguồn `javac` cho mọi bytecode được tạo bởi compiler/công cụ khác; sự có mặt/vắng mặt của các member tổng hợp phụ thuộc cấu trúc và quá trình sinh mã.

### 5.6. Annotation, record, sealed và đặc tính không mã hóa bằng một modifier

- Annotation có cơ chế **retention**. `@Override` có `RetentionPolicy.SOURCE`, không tồn tại trong class file đầu ra do `javac` tạo; không thể lấy lại bằng cách nhìn access flags. Các annotation được lưu ở retention khác có metadata riêng và Reflection thường chỉ cho phép truy vấn trực tiếp các annotation có retention `RUNTIME`.
- `record` (Java 16+) có metadata về record components, có thể hỏi `Class.isRecord()` và `getRecordComponents()`. `Modifier.isFinal(...)` không chứng minh một class là record; class `final` thông thường cũng final.
- `sealed` (Java 17+) liên quan đến danh sách subtype được phép, đọc qua `isSealed()` và `getPermittedSubclasses()`, tương ứng metadata `PermittedSubclasses`. Không thể dựng lại chính xác chuỗi từ khóa `permits` hoặc cách viết `non-sealed` chỉ bằng `getModifiers()`.
- Method `default` của interface có body và Reflection hỗ trợ `Method.isDefault()`. Không có `Modifier.isDefault(...)`; chỉ xem những bit modifier phổ biến là chưa đủ.

Một attribute riêng có thể giữ lại **một phần** ý nghĩa nguồn, nhưng vẫn không cung cấp toàn bộ cú pháp nguyên văn.

### 5.7. Nested class và nguồn gốc của `static`

Xét:

```java
class Outer {
    static class Nested {
    }
}
```

`Nested` là lớp thành viên `static` trong Java. `Nested.class.getModifiers()` có thể báo `static` vì Reflection xét thông tin thành viên lớp lồng. Trong class file, thông tin này liên quan tới `InnerClasses` attribute; đừng tưởng rằng mọi flag mà `Class.getModifiers()` trả về đều nằm trực tiếp trong `access_flags` của class header.

Đây là ví dụ điển hình cho việc phải xác định **đang đọc cấu trúc class-file nào** và **API Reflection nào đã diễn giải cấu trúc đó**.

## 6. Những gì không được kết luận từ flags

| Quan sát được | Có thể kết luận | Không đủ dữ liệu để kết luận |
| --- | --- | --- |
| `Modifier.isPublic(...) == true` | Thành viên/kiểu có quyền truy cập `public` theo mô hình Reflection | `public` đã được gõ tường minh trong source |
| `Modifier.isAbstract(...) == true` | Phần tử được phản ánh có tính chất `abstract` | Từ khóa `abstract` xuất hiện ở đúng vị trí/cách viết đó |
| `Modifier.isFinal(field.getModifiers())` | Field có thuộc tính `final` | Biểu thức khởi tạo, thứ tự field, ý nghĩa business |
| `Method.isVarArgs() == true` | Method có dấu hiệu varargs ở class file/runtime | Mọi token hoặc vị trí xuống dòng của khai báo nguồn |
| `Method.isSynthetic() == true` | Member được đánh dấu synthetic | Có một khai báo viết tay tương ứng |
| `Method.isBridge() == true` | Đây là bridge method theo Reflection | Người viết source đã tạo một method riêng với chính chữ ký bridge |
| `Field.getType() == List.class` | Kiểu field sau erasure là `List` | Tham số generic chính xác nếu thiếu `Signature` |
| `Class.isRecord() == true` | Runtime nhận diện kiểu record | Toàn bộ văn bản khai báo record gốc |
| `Class.isSealed() == true` | Runtime nhận diện kiểu sealed | Cách sắp xếp, viết tên, import và formatting của `permits` |
| `javap -c` in bytecode | Những chỉ thị JVM của phương thức đã biên dịch | Chính xác cấu trúc `if`/`switch`, tên biến và comment nguồn |

Ví dụ về tính chất nhiều-đến-một: một tác giả có thể viết `import java.util.List; List<String> values;`, còn tác giả khác viết `java.util.List<String> values;`. Hai cách viết thể hiện cùng kiểu thành viên và hoàn toàn có thể biên dịch thành metadata kiểu tương đương. Access flags không chứa lựa chọn cú pháp này.

## 7. Cách thực hành đúng với Reflection và class file

Khi cần khảo sát API Java hoặc xây công cụ documentation/static analysis, hãy phân biệt mục tiêu:

1. **Cần quyền truy cập hoặc thuộc tính runtime?** Dùng `getModifiers()`, `Modifier.isXxx(...)` và `Modifier.toString(...)`; đọc đúng loại member.
2. **Cần cấu trúc JVM?** Dùng `javap -v -p` hoặc thư viện đọc class file để phân tích class header, fields, methods, descriptors, flags và attributes. Kiểm tra nơi chứa metadata thay vì tìm tất cả trong một số nguyên.
3. **Cần thuộc tính nằm ngoài modifier?** Sử dụng API riêng như `isVarArgs()`, `isBridge()`, `isSynthetic()`, `isDefault()`, `isRecord()`, `isSealed()`, `getGenericType()` và `isNamePresent()` khi phù hợp.
4. **Cần tái tạo chính xác Java source?** Truy cập chính **tệp `.java`** và sử dụng parser Java (AST) nếu cần danh sách token, biểu thức, import, comment, annotation và trật tự nguồn. Bytecode decompiler chỉ cho mã nguồn *gần đúng*, không bảo đảm bản gốc.

Có thể dựng tài liệu mang nghĩa như “field được công khai”, “method là varargs”, hoặc “class là record”; đừng tuyên bố “tác giả đã viết nguyên văn khai báo này” khi chỉ có `.class`.

### Kiểm tra tự học

Phân loại các phát biểu sau là **đúng** hay **sai**:

1. `Modifier.toString(method.getModifiers())` tái hiện đúng tất cả từ khóa tác giả đã gõ trong khai báo.
2. Một method interface viết `void run();` có thể được Reflection báo là `public abstract`.
3. Nếu một parameter có `Class<?>` là `String[].class` thì đủ để biết tác giả đã dùng `String...`.
4. Một member xuất hiện trong `getDeclaredMethods()` có thể là method do compiler tạo.
5. `javap -v` đọc được class-file flags và attributes nhưng không bảo đảm phục hồi chính xác comment/import/spacing trong `.java`.
6. Nếu `getModifiers()` thiếu thông tin record hoặc sealed thì `Class` không có API nào khác để kiểm tra các thuộc tính đó.

**Đáp án:** (1) Sai; (2) Đúng; (3) Sai, cần `isVarArgs()` để nhận biết metadata varargs; (4) Đúng; (5) Đúng; (6) Sai, dùng `isRecord()` và `isSealed()` tương ứng.

## 8. Ghi nhớ

**Modifier/flag phản ánh trạng thái đã biên dịch, không phải bản ghi đầy đủ cú pháp nguồn.** Class file có flags, descriptors, bytecode và các attributes riêng; Reflection diễn giải một phần dữ liệu đó thành API thuận tiện. Cùng một thuộc tính hiệu lực có thể xuất phát từ từ khóa viết tường minh hoặc quy tắc ngầm định; một số đặc điểm dùng metadata ngoài `getModifiers()`; compiler còn có thể sinh thành viên không xuất hiện trực tiếp trong source. Khi cần chính xác cú pháp, thứ tự từ khóa, import, tên biến cục bộ, biểu thức hoặc comment, phải đọc nguồn `.java` và phân tích AST tương ứng.