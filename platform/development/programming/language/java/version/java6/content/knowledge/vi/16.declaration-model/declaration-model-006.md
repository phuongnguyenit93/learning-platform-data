# Types và kiểm tra quan hệ gán, kiểu con, xóa kiểu

## Mục tiêu

Trong mô hình khai báo và xử lý annotation của Java, tên lớp hiển thị bằng chuỗi không đủ để xác định hai kiểu có tương thích hay không. Sau bài học này, bạn có thể:

- Lấy `javax.lang.model.util.Types` từ `ProcessingEnvironment.getTypeUtils()` và lấy `TypeMirror` của trường, lớp hoặc thành phần nguồn qua mô hình `Element`.
- Phân biệt `Types.isAssignable(from, to)` (có thể gán), `Types.isSubtype(sub, super)` (quan hệ kiểu con) và `Types.isSameType(a, b)` (cùng kiểu theo mô hình compiler).
- Dùng `Types.erasure(type)` để hiểu **type erasure** của generics; không đánh đồng hai generic types khác tham số chỉ vì erasure của chúng bằng nhau.
- Nhận biết **bất biến tham số kiểu** (generic invariance), wildcard, widening primitive và boxing; kiểm tra các ví dụ đúng/sai bằng một annotation processor hoạt động thực tế.
- Áp dụng các API này để kiểm tra field, method hoặc contract trong processor mà không dùng `Class.forName` hay `TypeMirror.toString()` làm phép so sánh ngữ nghĩa.
- Tránh lỗi với `ErrorType`, wildcard, nguồn chưa phân giải đầy đủ, các kiểu không được một phép toán hỗ trợ và vòng đời annotation processing.

Các API thuộc module chuẩn `java.compiler`, **vẫn hiện hành và được hỗ trợ trong Java hiện đại**. Bài thực hành tương thích Java 17+ và đã được biên dịch, chạy bằng JDK 24. Không dựa vào cách làm đã legacy.

## 1. Types là gì? Vì sao phải dùng mô hình kiểu của compiler?

Trong một annotation processor, bạn có thể đọc:

```java
TypeElement classElement = processingEnv.getElementUtils()
        .getTypeElement("java.util.List");
TypeMirror type = classElement.asType();
Types types = processingEnv.getTypeUtils();
```

Đây là **đoạn dùng trong processor đã được khởi tạo**, không phải đoạn `main` độc lập: `processingEnv` do `AbstractProcessor` nhận từ môi trường biên dịch.

Có ba lớp khái niệm:

| Đối tượng | Mục đích | Ví dụ |
| --- | --- | --- |
| `Element` / `TypeElement` / `VariableElement` | Đại diện **khai báo** trong mã Java: class, interface, trường, method... | Khai báo field `List<String> names` |
| `TypeMirror` | Đại diện **kiểu** của một biểu thức/khai báo trong mô hình compile-time | Kiểu của field là `java.util.List<java.lang.String>` |
| `Types` | Các phép toán ngữ nghĩa trên `TypeMirror`: cùng kiểu, kiểu con, gán được, erasure, boxing, v.v. | Kiểm tra `List<String>` có thể gán vào `List<?>` hay không |

Sự khác biệt quan trọng là **khai báo** và **kiểu của khai báo** không phải một. Một `TypeElement` cho `java.util.List` biểu diễn khai báo generic `List<E>`. Còn field `List<String>` có một `DeclaredType` thể hiện một lần sử dụng cụ thể của generic đó.

```text
Java source:
  List<String> names;
  List<Integer> ids;
         |
         v
VariableElement --asType()--> TypeMirror
                                |
                                +--> Types.isSameType(...)
                                +--> Types.isSubtype(...)
                                +--> Types.isAssignable(...)
                                +--> Types.erasure(...)
```

Các API thuộc `javax.lang.model`. Dùng chúng trong **annotation processing/compile-time tooling**, không phải reflection runtime.

### So với reflection runtime

- `java.lang.reflect.Type` và `Class<?>` phản ánh thông tin có thể truy cập khi chương trình đã nạp class.
- `TypeMirror` biểu diễn kiểu **trong compiler**, kể cả nguồn vừa được biên dịch và chưa có class file.
- `Types` biết quy tắc Java language model, parameterized types, capture và subtype. Nó không phải `java.lang.reflect.Type` hay một helper lấy thông tin từ `Class.forName(...)`.
- `Class.isAssignableFrom(...)` có **chiều tham số ngược về cách đọc** so với `types.isAssignable(from, to)`, và runtime `Class` không giữ nguyên thông tin `List<String>` so với `List<Integer>` như mô hình compile-time.

Vì vậy, processor muốn xác nhận một trường có thể dùng ở vị trí tham số kiểu nào đó nên dùng `Types`, không chuyển `TypeMirror` thành tên rồi đem so sánh chuỗi.

## 2. Lấy Types và TypeMirror một cách đúng đắn

Trong processor kế thừa `AbstractProcessor`:

```java
Types types = processingEnv.getTypeUtils();
```

`processingEnv` chỉ sẵn sàng sau khi công cụ gọi `init(ProcessingEnvironment)`. Đừng dùng nó từ constructor của processor hoặc trước khi được compiler khởi tạo.

Để lấy kiểu từ một field:

```java
// Đoạn trong process(...), với Element owner trỏ tới một class.
for (VariableElement field :
        ElementFilter.fieldsIn(owner.getEnclosedElements())) {
    TypeMirror fieldType = field.asType();
    System.out.println(field.getSimpleName() + ": " + fieldType);
}
```

Đoạn này cần import `javax.lang.model.element.VariableElement`, `javax.lang.model.type.TypeMirror` và `javax.lang.model.util.ElementFilter`; chỉ là trích đoạn bổ sung, không phải chương trình `main`.

Đối với primitive, có thể lấy kiểu trực tiếp:

```java
TypeMirror intType = types.getPrimitiveType(TypeKind.INT);
TypeMirror longType = types.getPrimitiveType(TypeKind.LONG);
```

Đối với declared type của class biết tên:

```java
TypeMirror integerType = processingEnv.getElementUtils()
        .getTypeElement("java.lang.Integer").asType();
```

`getTypeElement(...)` có thể trả `null` nếu không tìm được lớp trong environment tương ứng; ứng dụng thật cần kiểm tra `null` trước khi gọi `asType()`. Với những kiểu tham số hóa, lấy `TypeMirror` trực tiếp từ một field/parameter trong mã nguồn hoặc xây qua `Types.getDeclaredType(...)` với đúng số type arguments; không tự lắp tên generic rồi hy vọng compiler phân giải chuỗi đó.

**Không so sánh `TypeMirror` bằng `==` hoặc `equals(...)` để khẳng định cùng kiểu.** API không bảo đảm cùng một kiểu luôn được đại diện bởi cùng một object, và `equals` không phải phép so sánh ngữ nghĩa Java type. Dùng `Types.isSameType(...)`.

## 3. `isAssignable(from, to)` — kiểm tra quan hệ gán

Chữ ký:

```java
boolean isAssignable(TypeMirror from, TypeMirror to)
```

Đọc như câu hỏi: **Một giá trị có kiểu `from` có thể được gán vào một biến/đích có kiểu `to` trong assignment context hay không?**

Ví dụ Java source:

```java
List<String> a = new ArrayList<String>();  // được phép
List<?> any = a;                           // được phép
// List<Integer> bad = a;                   // không hợp lệ
// List<Object> alsoBad = a;                // không hợp lệ
Integer boxed = 42;                        // boxing, được phép
```

Đây là **đoạn minh họa quy tắc kiểu**, không phải một file độc lập: cần import `java.util.List` và `java.util.ArrayList`; hai dòng sai cố ý được comment để source còn biên dịch.

Tương ứng trong processor:

```java
types.isAssignable(arrayListString, listString); // true
types.isAssignable(listString, listWildcard);     // true
types.isAssignable(listString, listInteger);      // false
types.isAssignable(listString, listObject);       // false
types.isAssignable(intType, integerType);         // true (boxing)
```

Các biến `TypeMirror` được khai báo trong demo chạy hoàn chỉnh bên dưới. Trong đó:

- `ArrayList<String>` implement `List<String>` nên có thể dùng ở vị trí đích `List<String>`.
- `List<String>` có thể gán vào `List<?>` vì wildcard biểu diễn những phần tử có kiểu chưa biết.
- `List<String>` **không thể** gán vào `List<Integer>` hoặc `List<Object>` chỉ vì `String` có quan hệ với `Object`. Generic `List<T>` trong trường hợp này **bất biến** theo `T`.
- `int` có thể gán vào `Integer` nhờ **boxing conversion** (`int` → `Integer`) trong assignment context.

Kết quả `isAssignable` phụ thuộc quy tắc gán của Java (JLS `5.2), không phải chỉ nhìn quan hệ kế thừa trực tiếp. Cần phân biệt phép toán này với **phép ép kiểu tường minh**: có thể cast một số biểu thức khi phép gán trực tiếp không hợp lệ, nhưng `isAssignable` không phải API hỏi “có thể cast hay không”.

**Chiều truyền:** `isAssignable(sourceType, targetType)`. Đảo đối số là hỏi câu khác; đặc biệt dễ sai khi kiểm tra subtype của collection hoặc interface.

## 4. `isSubtype(sub, super)` — quan hệ kiểu con

Chữ ký:

```java
boolean isSubtype(TypeMirror sub, TypeMirror sup)
```

Đọc là: **`sub` có phải subtype của `sup` theo hệ thống kiểu Java không?**

```java
types.isSubtype(arrayListString, listString); // true
types.isSubtype(listString, listWildcard);     // true
types.isSubtype(intType, longType);            // true
types.isSubtype(intType, integerType);         // false
```

Hai điểm quan trọng:

1. Với references, subtype xuất phát từ superclass/interface và quan hệ của các parameterized types. `ArrayList<String>` là subtype của `List<String>`. Quan hệ với wildcard như `List<String>` → `List<?>` cũng được hệ thống kiểu Java hỗ trợ.
2. **Primitive types cũng có quan hệ subtyping trong JLS.** Ví dụ `int` là subtype của `long`, nên `isSubtype(int, long)` là `true`. Đừng ghi nhớ sai rằng `isSubtype` “chỉ nói về class/interface”.

### Khác biệt quan trọng giữa `isSubtype` và `isAssignable`

Với `int` và `Integer`:

```java
types.isSubtype(intType, integerType);     // false
types.isAssignable(intType, integerType);  // true
```

`int` **không phải subtype của `Integer`**, nhưng trong assignment context, boxing cho phép gán giá trị `int` vào `Integer`. Đây là ví dụ rõ ràng rằng **assignability rộng hơn việc chỉ kiểm tra subtype**.

Với `int` sang `long`, cả hai trả `true` (theo ngữ nghĩa subtype/widening của primitive). Vì thế **không dùng cặp `int`/`long` để minh họa chúng luôn khác nhau**.

Bảng đối chiếu:

| From/sub | To/super | `isSubtype` | `isAssignable` | Lý do |
| --- | --- | --- | --- | --- |
| `ArrayList<String>` | `List<String>` | `true` | `true` | Interface implementation |
| `List<String>` | `List<Integer>` | `false` | `false` | Generic types không tương thích |
| `List<String>` | `List<Object>` | `false` | `false` | Generic invariance |
| `List<String>` | `List<?>` | `true` | `true` | Wildcard supertype |
| `int` | `long` | `true` | `true` | Primitive widening/subtyping |
| `int` | `Integer` | `false` | `true` | Boxing là assignment conversion |

Các giá trị trên là kết quả của chương trình processor chạy kiểm thử trên JDK 24, với `--release 17`.

## 5. `isSameType(a, b)` — so sánh ngữ nghĩa kiểu

Chữ ký:

```java
boolean isSameType(TypeMirror a, TypeMirror b)
```

Ví dụ:

```java
types.isSameType(listString, listInteger); // false
types.isSameType(listString, listString);  // true
```

Cùng generic declaration `java.util.List` **không đồng nghĩa cùng generic type**:

- `List<String>` và `List<Integer>` không phải cùng kiểu.
- `List<String>` ở hai field khác nhau có thể vẫn là cùng kiểu về mặt ngữ nghĩa, ngay cả khi `TypeMirror` lấy được là hai object khác nhau.
- `isSameType(...)` là cách API quy định để kiểm tra, thay vì `TypeMirror.equals(...)` hoặc `toString()`.

### Bẫy đặc biệt: wildcard

Theo hợp đồng của `Types.isSameType`, **nếu một trong hai tham số chính là wildcard type**, phương thức trả `false`, kể cả bạn truyền **cùng một object wildcard** hai lần.

```java
TypeMirror wildcard =
        ((DeclaredType) listWildcard).getTypeArguments().get(0);

boolean sameWildcard = types.isSameType(wildcard, wildcard); // false
```

`listWildcard` ở đây là `TypeMirror` của `List<?>` trong demo hoàn chỉnh, có `TypeKind.DECLARED` nên có thể ép sang `DeclaredType` và lấy type argument. Đây là một trường hợp **đặc biệt của chính wildcard**, không mâu thuẫn với việc `List<?>` có thể làm target gán cho `List<String>`.

Không kết luận từ caveat wildcard rằng mọi dạng “kiểu có wildcard” đều không so sánh được. Hãy phân biệt `WildcardType` trực tiếp và `DeclaredType` chứa wildcard arguments; kiểm tra theo contract cụ thể của API.

**Thêm một chi tiết:** annotation gắn lên *type use* không quyết định `isSameType`, vì đó là metadata của type. Khi phân tích type annotations, kiểm tra `getAnnotationMirrors()` riêng thay vì coi `isSameType` là phép so sánh cả annotation.

## 6. `erasure(type)` — xóa tham số generic, không xóa kiểu nguồn

Chữ ký:

```java
TypeMirror erasure(TypeMirror type)
```

Với hai kiểu parameterized:

```text
List<String>   --erasure-->  java.util.List   (raw type)
List<Integer>  --erasure-->  java.util.List   (raw type)
```

Trong processor:

```java
TypeMirror e1 = types.erasure(listString);
TypeMirror e2 = types.erasure(listInteger);

types.isSameType(listString, listInteger); // false
types.isSameType(e1, e2);                  // true
System.out.println(e1);                  // java.util.List
```

**Điểm cốt lõi:** `erasure` trả một **TypeMirror khác thể hiện kiểu sau xóa generic theo JLS `4.6**, không sửa mã nguồn của người học, không lập tức thay đổi khai báo field, và không làm `List<String>` gán an toàn vào `List<Integer>`.

### Tại sao hai erasure giống nhau không đủ để cho phép gán?

`List<String>` và `List<Integer>` đều có erasure `List`, nhưng:

```java
List<String> text = new ArrayList<>();
// List<Integer> numbers = text; // sai và bị compiler từ chối
```

Nếu processor chỉ so sánh:

```java
types.isSameType(
        types.erasure(listString),
        types.erasure(listInteger)); // true
```

rồi kết luận hai kiểu có thể gán qua lại thì **đã mất thông tin an toàn generic**. Erasure hữu ích khi phân tích binary signature, một số quy tắc override/bridge, hoặc khi cần so sánh generic declarations theo dạng đã xóa tham số; nó không phải phép thay thế cho `isAssignable`.

### Raw types và unchecked conversions

Trong Java còn có **raw types** và **unchecked conversions**. Một assignment liên quan raw generic có thể được phép kèm cảnh báo; kiểu sau erasure giúp hiểu vì sao runtime chỉ thấy raw declaration, nhưng mọi kết luận về việc phép gán cụ thể được compiler cho phép phải hỏi `Types.isAssignable` trên **cặp type thực sự cần kiểm tra**, không suy ra trực tiếp từ `isSameType(erasure(a),erasure(b))`.

Nếu phân tích generic method, type variable có thể erasure về **bound** của nó (nếu không có bound tường minh thì thường là `Object`); với array, erasure được áp dụng trên component type theo quy tắc JLS. Đừng mô tả erasure như một chuỗi thao tác “cắt tất cả phần sau dấu `<`” vì không đúng cho mọi `TypeMirror`.

## 7. Ví dụ chạy được Java 17+: annotation processor kiểm tra 14 trường hợp

Ta dùng `javax.annotation.processing.AbstractProcessor` để đọc các field types trong class có annotation `@CheckTypes`. Processor in và **assert kỳ vọng**: nếu phép kiểm tra cho kết quả bất ngờ, nó ném `AssertionError` khiến lệnh javac thất bại. Như vậy phần output được kiểm chứng bằng hành vi thực, không chỉ là log mô tả.

### 7.1. Cấu trúc thư mục

```text
types-demo/
├── processor/
│   └── demo/
│       └── processor/
│           └── TypesInspector.java
├── src/
│   └── demo/
│       ├── CheckTypes.java
│       └── ModelCases.java
└── out/
    ├── processor/  (tạo trong lệnh build)
    └── classes/    (tạo trong lệnh build)
```

Ta **chủ động chỉ định processor** khi gọi javac. Không dựa vào default tự tìm processor trên classpath (đặc biệt với JDK 23+).

### 7.2. Annotation kiểm tra: `src/demo/CheckTypes.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface CheckTypes {}
```

`@CheckTypes` là marker để processor biết class nào cần kiểm tra. Vì đây là ví dụ compile-time tooling, `RetentionPolicy.SOURCE` là đủ, không cần reflection runtime.

### 7.3. Source fixture: `src/demo/ModelCases.java`

```java
package demo;

import java.util.ArrayList;
import java.util.List;

@CheckTypes
class ModelCases {
    List<String> text;
    List<Integer> numbers;
    List<Object> objects;
    List<?> unknown;
    ArrayList<String> array;
}
```

Các field được cố ý khai báo khác nhau để processor lấy `TypeMirror` và kiểm tra thật. Lưu ý `List<String>`, `List<Integer>` và `List<Object>` đều tham chiếu cùng generic interface `List` nhưng khác *type arguments*.

### 7.4. Processor đầy đủ: `processor/demo/processor/TypesInspector.java`

```java
package demo.processor;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeKind;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.ElementFilter;
import javax.lang.model.util.Types;

@SupportedAnnotationTypes("demo.CheckTypes")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class TypesInspector extends AbstractProcessor {
    private boolean done;

    private static TypeMirror fieldType(Element parent, String name) {
        for (VariableElement f : ElementFilter.fieldsIn(parent.getEnclosedElements())) {
            if (f.getSimpleName().contentEquals(name)) return f.asType();
        }
        throw new IllegalArgumentException("Missing field: " + name);
    }

    private static void check(String name, boolean actual, boolean expected) {
        if (actual != expected) throw new AssertionError(name + " was " + actual);
        System.out.println(name + "=" + actual);
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (done || round.processingOver()) return true;
        TypeElement marker = processingEnv.getElementUtils()
                .getTypeElement("demo.CheckTypes");
        for (Element type : round.getElementsAnnotatedWith(marker)) {
            Types types = processingEnv.getTypeUtils();
            TypeMirror ls = fieldType(type,"text");
            TypeMirror li = fieldType(type,"numbers");
            TypeMirror lo = fieldType(type,"objects");
            TypeMirror lw = fieldType(type,"unknown");
            TypeMirror als = fieldType(type,"array");
            TypeMirror primInt = types.getPrimitiveType(TypeKind.INT);
            TypeMirror primLong = types.getPrimitiveType(TypeKind.LONG);
            TypeMirror integer = processingEnv.getElementUtils()
                    .getTypeElement("java.lang.Integer").asType();
            check("subtype:ArrayList<String>->List<String>",
                    types.isSubtype(als,ls),true);
            check("assignable:ArrayList<String>->List<String>",
                    types.isAssignable(als,ls),true);
            check("assignable:List<String>->List<Integer>",
                    types.isAssignable(ls,li),false);
            check("assignable:List<String>->List<Object>",
                    types.isAssignable(ls,lo),false);
            check("assignable:List<String>->List<?>",
                    types.isAssignable(ls,lw),true);
            check("subtype:List<String>->List<?>",
                    types.isSubtype(ls,lw),true);
            check("same:List<String>,List<Integer>",
                    types.isSameType(ls,li),false);
            check("same:erasure(List<String>),erasure(List<Integer>)",
                    types.isSameType(types.erasure(ls),types.erasure(li)),true);
            System.out.println("erasure(List<String>)="+types.erasure(ls));
            check("subtype:int->long",types.isSubtype(primInt,primLong),true);
            check("assignable:int->long",types.isAssignable(primInt,primLong),true);
            check("subtype:int->Integer",types.isSubtype(primInt,integer),false);
            check("assignable:int->Integer",types.isAssignable(primInt,integer),true);
            TypeMirror wildcard = ((DeclaredType) lw).getTypeArguments().get(0);
            check("isSameType(wildcard,wildcard)",
                    types.isSameType(wildcard,wildcard),false);
            done=true;
        }
        return true;
    }
}
```

### Những chi tiết đáng chú ý trong processor

- `@SupportedAnnotationTypes("demo.CheckTypes")` giúp javac biết processor xử lý marker nào.
- `@SupportedSourceVersion(RELEASE_17)` khai báo source version được hỗ trợ, thống nhất với `--release 17` của demo. Đây là metadata của processor, **không phải** version của JDK đang khởi động compiler.
- `round.processingOver()` bỏ qua round cuối. `done` ngăn in và kiểm tra lặp lại ở round sau nếu compiler tạo thêm rounds.
- `ElementFilter.fieldsIn(parent.getEnclosedElements())` chỉ lấy **field declarations** rồi `asType()` lấy kiểu của chúng.
- `getTypeUtils()` cung cấp các phép so sánh theo Java type model; `getElementUtils()` cho phép tìm `TypeElement` theo tên đầy đủ.
- `types.getPrimitiveType(TypeKind.INT)` và `LONG` giúp tạo primitive types mà không cần khai báo thêm field mẫu.
- `check(...)` so sánh kết quả thực với kỳ vọng và ném `AssertionError` khi sai; đây là phép kiểm thử tự động tối giản.
- `TypeMirror wildcard` được lấy **từ type argument bên trong `List<?>`**, không phải bản thân `List<?>`; vì thế ví dụ kiểm tra đúng caveat wildcard của `isSameType`.

**Lưu ý phạm vi:** Processor này dùng `System.out.println` để làm bài thực hành dễ quan sát. Trong processor đưa vào thư viện, ưu tiên `processingEnv.getMessager()` cho cảnh báo/lỗi và quản lý kết quả kiểm tra theo contract ứng dụng; không dựa vào stdout của compiler như một giao thức lâu dài.

### 7.5. Lệnh chạy trên Windows PowerShell

Đứng ở thư mục `types-demo`:

```powershell
New-Item -ItemType Directory -Force out\processor, out\classes | Out-Null

javac --release 17 -d out\processor processor\demo\processor\TypesInspector.java

javac --release 17 -processorpath out\processor -processor demo.processor.TypesInspector -proc:only -d out\classes src\demo\CheckTypes.java src\demo\ModelCases.java
```

Đây là hai bước **khác nhau**: trước tiên biên dịch processor thành `.class`, sau đó javac sử dụng processor ấy để phân tích source fixture.

`-processorpath out\processor` cho công cụ biết nơi tìm processor; `-processor demo.processor.TypesInspector` chọn processor **tường minh**, hoạt động nhất quán với JDK 23+; `-proc:only` yêu cầu chỉ thực hiện annotation processing mà **không phát hành class files của `ModelCases`**. Mục tiêu test là quan hệ kiểu, không phải chạy `ModelCases.main()` (thực tế lớp này không có `main`).

### 7.6. Lệnh chạy trên Linux/macOS

```bash
mkdir -p out/processor out/classes

javac --release 17 -d out/processor \
  processor/demo/processor/TypesInspector.java

javac --release 17 \
  -processorpath out/processor \
  -processor demo.processor.TypesInspector \
  -proc:only \
  -d out/classes \
  src/demo/CheckTypes.java src/demo/ModelCases.java
```

Lệnh không cần Maven, Gradle hoặc thư viện bên ngoài JDK. Build tool production có thể cấu hình annotation processor path riêng thay vì chạy các lệnh thủ công.

### 7.7. Kết quả đã biên dịch và chạy với JDK 24

```text
subtype:ArrayList<String>->List<String>=true
assignable:ArrayList<String>->List<String>=true
assignable:List<String>->List<Integer>=false
assignable:List<String>->List<Object>=false
assignable:List<String>->List<?>=true
subtype:List<String>->List<?>=true
same:List<String>,List<Integer>=false
same:erasure(List<String>),erasure(List<Integer>)=true
erasure(List<String>)=java.util.List
subtype:int->long=true
assignable:int->long=true
subtype:int->Integer=false
assignable:int->Integer=true
isSameType(wildcard,wildcard)=false
```

Đây là các kết quả thực tế từ chương trình JDK 24 biên dịch với `--release 17`. Nếu một phép kiểm tra trả giá trị khác với kỳ vọng, processor ném `AssertionError` và `javac` không hoàn tất thành công; do đó các dòng log không chỉ là mô tả thủ công.

**Không nhầm với output file:** vì dùng `-proc:only` nên việc không có `out/classes/demo/ModelCases.class` **không phải lỗi**. Nếu muốn cả annotation processing và biên dịch class, dùng cấu hình compiler thực hiện đầy đủ các pha thay vì `-proc:only`.

## 8. Đọc và phân tích 14 kết quả

### 8.1. Kế thừa và generic interface

Hai dòng đầu `true` vì `ArrayList<String>` hiện thực `List<String>`. Đây là trường hợp `isSubtype` và `isAssignable` cùng đồng ý.

### 8.2. Generic invariance

`List<String>` → `List<Integer>` và `List<Object>` đều `false` cho phép gán. Không có “generic covariance mặc định” cho `List<E>`: mặc dù `String` là subtype của `Object`, điều đó không biến `List<String>` thành subtype của `List<Object>`.

Tại sao? Nếu cho phép gán rồi gọi `listOfObjects.add(new Object())`, collection vốn khai báo chỉ chứa String sẽ bị phá vỡ type safety. Java dùng invariance cho generic declarations dạng này và cung cấp wildcard để diễn đạt những quan hệ phù hợp.

### 8.3. Wildcard làm target tổng quát

`List<String>` có thể gán vào `List<?>`; cả `isAssignable` và `isSubtype` trong demo trả `true`. Nhưng một `List<?>` không có nghĩa consumer được chèn tùy ý một `String` hay `Object` mới vào nó: kiểu phần tử thực sự không biết, nên nhiều thao tác ghi bị type checker từ chối.

### 8.4. Erasure có thể giống dù kiểu nguyên bản khác

`isSameType(List<String>, List<Integer>)` là `false`. Sau khi erasure, cả hai là `java.util.List`, nên `isSameType(erasure(...), erasure(...))` là `true`. Đây là câu trả lời của **hai câu hỏi khác nhau**, không phải mâu thuẫn.

### 8.5. Primitive widening so với boxing

`int` → `long` được công nhận cả về subtyping và assignment. `int` → `Integer` lại khác: assignment được phép do boxing, nhưng không tạo quan hệ subtype giữa primitive `int` và wrapper class `Integer`.

### 8.6. Tình huống wildcard tự so sánh

`isSameType(wildcard, wildcard) == false` là ngoại lệ được ghi rõ trong hợp đồng của `Types`. Không viết helper giả định tính phản xạ cho mọi `TypeMirror` thuộc kind `WILDCARD` rồi dùng nó để chứng minh hai wildcard là cùng kiểu.

## 9. Chọn phương thức nào cho các tình huống thực tế?

| Bài toán | API nên dùng | Lưu ý |
| --- | --- | --- |
| Field có thể truyền cho tham số method có kiểu `target`? | `isAssignable(fieldType, targetType)` | Phù hợp với assignment conversion; cần đúng chiều. |
| Field có đúng thuộc một họ kiểu/subtype? | `isSubtype(fieldType, requiredSuperType)` | Có thể chấp nhận subclass/interface. |
| Hai generic usages có phải cùng kiểu? | `isSameType(a, b)` | Không dùng `equals`; chú ý wildcard trực tiếp. |
| Hai types có cùng hình dạng sau type erasure? | `isSameType(erasure(a), erasure(b))` | Không dùng để khẳng định generic assignment an toàn. |
| Muốn kiểm tra từ kiểu `int` sang `Integer`? | `isAssignable(int, integerType)` | Boxing làm `true`; `isSubtype` vẫn `false`. |
| Muốn biết direct superclass/interfaces? | `directSupertypes(type)` | Không thay thế tổng thể phép kiểm tra subtype. |
| Muốn phân tích kiểu của một member trong `List<String>`? | `asMemberOf(declaredType, memberElement)` | Áp dụng type substitutions trong ngữ cảnh owner. |
| Muốn mô hình hóa type tham số hóa theo TypeElement? | `getDeclaredType(typeElem, typeArgs...)` | Bảo đảm số lượng/kiểu arguments đúng. |

Một processor kiểm tra hợp đồng kiểu nên **đặt tên phép kiểm tra theo câu hỏi thực tế**, ví dụ `canAssignValueTo(fieldType, parameterType)`, thay vì một helper chung tên `isCompatible` không chỉ rõ chiều và quy tắc. Điều này làm code review đơn giản hơn và giảm lỗi đảo đối số.

## 10. Khi nào cần thêm các thao tác Types khác?

Ngoài bốn phép toán chính, `Types` còn có các tiện ích hiện hành:

- `getPrimitiveType(TypeKind)`: tạo primitive type mirrors cho phép kiểm tra.
- `boxedClass(PrimitiveType)` và `unboxedType(TypeMirror)`: tra kiểu tương ứng của wrapper và primitive; không tự thực thi phép boxing runtime.
- `getArrayType(componentType)`: tạo array type.
- `getDeclaredType(TypeElement, TypeMirror...)`: xây declared type với type arguments, hữu ích nếu không lấy trực tiếp từ source field.
- `getWildcardType(extendsBound, superBound)`: tạo wildcard type có bounds.
- `capture(type)`: thực hiện capture conversion trên type model, hữu ích khi phân tích wildcard/generics phức tạp.
- `directSupertypes(type)`: trả các direct supertypes theo ngữ nghĩa JLS.
- `asMemberOf(containing, member)`: giải quyết kiểu member trong ngữ cảnh parameterized enclosing type.

Ví dụ về `asMemberOf`: member `List<E>.get(int)` có return type liên quan `E`; khi xem dưới góc `List<String>`, cần nhận return type `String` bằng phép thay thế generic tương ứng, chứ không chỉ lấy declaration ban đầu. Đây là câu hỏi về **kiểu của member trong ngữ cảnh**, khác với `erasure`.

Không cần ép mọi processor phải dùng toàn bộ API. Với các validation kiểu thông thường, `getTypeUtils`, `isAssignable`, `isSubtype`, `isSameType` và `erasure` đã giải quyết phần lớn tình huống trọng tâm của bài.

## 11. ErrorType, loại TypeMirror và vòng xử lý

Trong quá trình biên dịch, một kiểu có thể **chưa được phân giải** do thiếu dependency hoặc do source sinh trong round sau. `TypeMirror.getKind()` có thể là `TypeKind.ERROR`; lớp mô hình `ErrorType` biểu diễn kiểu lỗi. Đây không phải bằng chứng chắc chắn rằng mọi phép so sánh sẽ trả `false` như kiểu không tương thích thông thường.

**Nên làm:**

1. Kiểm tra `TypeKind.ERROR` hoặc các kiểu chưa giải quyết trước khi ra quyết định quan trọng.
2. Nếu biết một generated type chỉ xuất hiện ở round sau, thiết kế processor để xử lý đúng vòng đời và không lưu giữ quá mức assumptions về type mirrors cũ.
3. Dùng `Messager` để phát diagnostics hữu ích, thay vì im lặng bỏ qua dependency thiếu.
4. Chỉ so sánh những loại kiểu mà phương thức được áp dụng cho phép.

Theo Javadoc của `Types`, nhiều phương thức như `isSubtype`, `isAssignable` có thể ném `IllegalArgumentException` với những type không thuộc phạm vi như `ExecutableType`, package hoặc module pseudo-types. `erasure` cũng không được gọi tùy tiện cho package/module types. API không phải một toán tử tổng quát có nghĩa cho **mọi** `TypeMirror`.

`TypeMirror.toString()` hữu ích để hiển thị, nhưng Javadoc chỉ hứa dạng mô tả phù hợp khi có thể, không biến chuỗi đó thành hệ thống định danh/type checking chuẩn. Dùng `getKind()`, `DeclaredType`, `TypeVariable`, `TypeVisitor` và các phép của `Types` khi cần phân tích ngữ nghĩa.

## 12. Những sai lầm thường gặp

### Sai lầm 1 — Đảo `from` và `to`

`types.isAssignable(a, b)` hỏi “a có thể gán vào b không?”. Đảo thành `isAssignable(b, a)` có thể đổi kết quả; với quan hệ lớp cha/con, điều này đặc biệt dễ mắc.

### Sai lầm 2 — Coi `isAssignable` và `isSubtype` là đồng nghĩa tuyệt đối

Boxing `int` → `Integer` làm `isAssignable` trả `true` nhưng `isSubtype` trả `false`. Quy tắc assignment context rộng hơn subtype đơn thuần.

### Sai lầm 3 — Nghĩ generic type tham số hóa tự động covariance

`List<String>` không gán vào `List<Object>`. Dùng wildcard đúng nếu hợp đồng cần đọc nhiều loại phần tử, hoặc thiết kế API generic phù hợp; không bỏ type safety bằng raw cast.

### Sai lầm 4 — So sánh `TypeMirror` bằng `==`, `equals` hoặc chuỗi

Hai type mirrors có thể không phải cùng object mà vẫn biểu diễn cùng kiểu; `toString()` không phải bộ kiểm tra type compatibility. Dùng `Types.isSameType`.

### Sai lầm 5 — Dùng erasure để “hợp thức hóa” generic assignment

`List<String>` và `List<Integer>` có cùng erasure, nhưng không thể tự ý gán qua lại. Erasure phục vụ một câu hỏi khác.

### Sai lầm 6 — Nghĩ primitive không thể có subtype

Trong Java type model, `int` là subtype của `long`. Sự khác biệt boxing cần được minh họa bằng `int` và `Integer`.

### Sai lầm 7 — Coi wildcard trực tiếp là cùng kiểu với chính nó

`Types.isSameType(wildcard, wildcard)` trả `false` theo contract. Khi viết thuật toán tổng quát, phải xử lý đặc điểm này.

### Sai lầm 8 — Cố so sánh kiểu chưa được phân giải như kiểu đã hợp lệ

`ErrorType` có thể xuất hiện do thiếu class hoặc quá trình generation. Kiểm tra lỗi resolution và rounds, không mặc định mọi phép `Types` sẽ có ý nghĩa như với declared types đầy đủ.

### Sai lầm 9 — Dùng reflection để kiểm tra source chưa biên dịch

`Class.forName(...)` chỉ phù hợp với class có thể nạp ở runtime. Annotation processor làm việc trên compiler model, gồm cả class chưa có bytecode. Dùng `Elements` và `Types`.

### Sai lầm 10 — Trông chờ javac tự chạy processor theo default cũ

Ví dụ dùng `-processor` và `-processorpath` tường minh. Với JDK 23+, annotation processing không nên được kỳ vọng tự kích hoạt chỉ vì có processor trong classpath. Cấu hình build rõ ràng và chỉ tin cậy processor được phép chạy.

## 13. Checklist QA cho processor kiểm tra kiểu

1. Processor được kích hoạt với đúng source version, dependency và annotation types.
2. Mỗi `TypeMirror` được lấy từ field, parameter, method hoặc `Elements`/`Types` đúng ngữ cảnh.
3. Dùng `isAssignable(from, to)` nếu cần điều kiện **gán được**.
4. Dùng `isSubtype(sub, super)` nếu cần quan hệ **kiểu con**.
5. Dùng `isSameType` nếu cần so sánh **hai kiểu** thay vì object identity.
6. Dùng `erasure` khi thật sự cần kiểm tra kiểu **sau xóa tham số generic**, không thay cho assignment.
7. Có test với `List<String>`, `List<Integer>`, `List<?>`, primitive widening và boxing.
8. Có test cho wildcard caveat của `isSameType` khi viết code tổng quát.
9. Kiểm tra `TypeKind.ERROR` và các type không hỗ trợ nếu source hoặc dependency có thể lỗi.
10. Dùng `Messager` báo lỗi tại đúng `Element` khi validation không đạt trong sản phẩm thật.
11. Thực thi bằng lệnh/build tool tạo môi trường sạch, processor path explicit; kiểm tra cả positive và negative scenarios.
12. Không chạy mã source từ người dùng chỉ để kiểm tra một quan hệ kiểu: đây là công việc compile-time, không cần class loading runtime.

## 14. Tự kiểm tra

**1.** Muốn xem `List<String>` có gán vào một biến `List<?>` không, dùng gì?

**Đáp:** Lấy `TypeMirror` của cả hai rồi gọi `types.isAssignable(listString, listWildcard)`. Trong ví dụ, kết quả `true`.

**2.** `ArrayList<String>` có là subtype của `List<String>` không?

**Đáp:** Có. `types.isSubtype(arrayListString, listString)` trả `true`.

**3.** `List<String>` có gán vào `List<Object>` không?

**Đáp:** Không. Type argument invariance khiến phép gán đó không hợp lệ; `isAssignable` trả `false`.

**4.** `int` có là subtype của `long` không?

**Đáp:** Có theo quan hệ primitive subtyping của Java; `isSubtype(int,long)` và `isAssignable(int,long)` cùng trả `true` trong demo.

**5.** `int` có là subtype của `Integer` không? Có thể gán không?

**Đáp:** Không là subtype (`false`), nhưng có thể gán (`true`) vì boxing conversion.

**6.** Nếu `isSameType(erasure(List<String>), erasure(List<Integer>)) == true`, có thể gán hai generic types này trực tiếp cho nhau không?

**Đáp:** Không suy ra được. Cả hai erasure là raw `List`, nhưng generic usages gốc vẫn khác và `isAssignable(List<String>,List<Integer>)` là `false`.

**7.** Tại sao không dùng `typeMirror.equals(...)` để kiểm tra Java type equality?

**Đáp:** `equals` chỉ tuân theo hợp đồng object, không bảo đảm cùng ý nghĩa với type equality. `Types.isSameType` là API chuyên dụng.

**8.** `isSameType(wildcard,wildcard)` luôn `true` nếu cùng object?

**Đáp:** Không. API quy định wildcard type trực tiếp là một ngoại lệ: phương thức trả `false`.

**9.** Tại sao ví dụ dùng `-proc:only` và không sinh `ModelCases.class`?

**Đáp:** Bài chỉ cần annotation processor phân tích source. `-proc:only` cố ý dừng sau annotation processing, không yêu cầu các class output thông thường.

**10.** Khi một field type chưa giải quyết được vì thiếu thư viện, nên làm gì?

**Đáp:** Kiểm tra tình trạng `ErrorType`/`TypeKind.ERROR` và diagnostics của compiler, bảo đảm classpath đúng hoặc xử lý phù hợp các vòng generation. Không coi nó như type hợp lệ rồi đưa ra kết luận ngữ nghĩa thiếu căn cứ.

## Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — `javax.lang.model.util.Types`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/Types.html): `isAssignable`, `isSubtype`, `isSameType`, `erasure`, `asMemberOf` và các phép toán type model.
- [Oracle Java SE 26 — `TypeMirror`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html): đại diện kiểu, `getKind()`, ý nghĩa của `equals`.
- [Oracle Java SE 26 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): `getTypeUtils()` và `getElementUtils()`.
- [Oracle Java SE 26 — `ElementFilter`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/ElementFilter.html): lọc field declarations bằng `fieldsIn(...)`.
- [Java Language Specification, Java SE 26 — Type Erasure `4.6](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.6) và [Subtyping `4.10](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.10): cơ sở ngữ nghĩa cho erasure/subtyping.
- [Java Language Specification, Java SE 26 — Assignment Contexts `5.2](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html#jls-5.2): những phép chuyển đổi có thể có khi gán, gồm boxing.
- [Oracle Java SE 26 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): các rounds xử lý và phần tử có annotation.

**Ghi nhớ:** `Types` là công cụ của **compiler type model**. `isSubtype` kiểm tra quan hệ kiểu con, `isAssignable` kiểm tra khả năng gán kể cả một số conversions như boxing, `isSameType` kiểm tra type equality có ngoại lệ wildcard trực tiếp, còn `erasure` trả kiểu sau xóa generics. Hỏi đúng câu hỏi và truyền đúng chiều type mirrors giúp annotation processor kiểm tra hợp đồng Java chính xác thay vì so sánh tên class hay raw generic types.
