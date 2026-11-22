# Phân biệt lớp được liệt kê với lớp có thể được sửa

> **Mục tiêu:** Khi khảo sát một JVM đang chạy bằng Java agent, biết đọc kết quả của `Instrumentation.getAllLoadedClasses()` mà **không nhầm một `Class<?>` được liệt kê với một class có thể `retransform` hoặc `redefine`**. Biết dùng `isModifiableClass`, kiểm tra capability JVM/agent, phân biệt `getInitiatedClasses`, array/primitive/hidden class, và xây quy trình chọn đúng mục tiêu trước mọi thao tác làm thay đổi bytecode. Bài có ví dụ Java 17+ hoàn chỉnh và **chỉ khảo sát, không sửa class**.

Đây là một kỹ năng thuộc nhóm **Khảo sát khi chạy** của Java Advanced Instrumentation. Một agent có thể nhìn thấy hàng nghìn class trong bộ nhớ, nhưng chỉ một phần phù hợp để sửa. Hai câu hỏi khác nhau cần được giải riêng:

1. **Lớp nào đã được JVM nạp tại thời điểm khảo sát?** → `getAllLoadedClasses()`.
2. **Một `Class<?>` cụ thể có thể là đối tượng sửa định nghĩa không?** → `isModifiableClass(clazz)`; và sau đó còn phải kiểm tra khả năng `retransform`/`redefine` của runtime.

Không thể suy ra câu trả lời thứ hai chỉ từ câu trả lời thứ nhất.

## 1. Bản đồ các quyết định

```text
JVM đang chạy
     │
     ▼
Instrumentation.getAllLoadedClasses()
     │       (danh sách Class<?> đã nạp tại thời điểm lấy mẫu)
     │
     ├─ Class thuộc loader/module/package nào?
     ├─ Class là array/primitive/hidden hoặc loại đặc biệt?
     ├─ Class đúng mục tiêu mà agent được phép xử lý?
     │
     ▼
Instrumentation.isModifiableClass(clazz)
     │
     ├─ false → KHÔNG thử redefine/retransform class đó
     │
     └─ true
           │
           ├─ Muốn retransform?
           │      └─ kiểm tra isRetransformClassesSupported()
           │
           └─ Muốn redefine?
                  └─ kiểm tra isRedefineClassesSupported()
                         │
                         ▼
              Còn phải bảo đảm:
              bytes hợp lệ, schema hợp lệ,
              transformer chain hợp lệ,
              class loader/module access,
              và JVM chấp nhận thao tác thực tế
```

**Một câu ghi nhớ:** *Listed* là tính chất của phép **khám phá**; *modifiable* là kết quả một phép **kiểm tra khả năng sửa trên một class**; *successfully modified* chỉ có thể khẳng định sau khi JVM đã hoàn tất yêu cầu cập nhật.

Không nên in thông báo “đã instrument 1.000 class” chỉ vì `getAllLoadedClasses()` trả 1.000 phần tử. Có thể không có class nào được sửa; việc liệt kê tự nó không chèn một instruction hay thay bytecode.

## 2. `getAllLoadedClasses()` thực sự trả về gì?

Chữ ký trong `java.lang.instrument.Instrumentation`:

```java
Class<?>[] loaded = instrumentation.getAllLoadedClasses();
```

Trong đó `instrumentation` phải do JVM truyền vào Java agent qua `premain`/`agentmain`; mã này không phải chương trình độc lập. Method trả về **mảng các `Class<?>` hiện đang được JVM nạp**. Tài liệu JDK 17 nói rõ nó bao gồm các class/interface thông thường, **hidden classes/interfaces** và **array classes** của nhiều loại.

Ví dụ những class **có thể** thấy trong quá trình khảo sát:

```text
java.lang.String
java.util.ArrayList
com.example.orders.OrderService
com.example.orders.OrderService$State
[Lcom.example.orders.OrderService;
[I
một hidden class do runtime sinh ra
```

Đây chỉ là **ví dụ tên**; không phải JVM nào cũng đã nạp đủ các lớp ấy tại đúng thời điểm chụp. `getAllLoadedClasses()` không có nghĩa “liệt kê tất cả các file `.class` có trên classpath” hoặc “liệt kê tất cả những class sẽ được tải trong tương lai”.

### Điều kết quả **có** và **không có** nghĩa

| Kết quả | Được phép kết luận | Không được phép suy ra |
| --- | --- | --- |
| `Class<?>` có trong `loaded` | Class đã được JVM nạp trong lần khảo sát | Class đó modifiable |
| `Class<?>` không có trong `loaded` | Nó không nằm trong snapshot vừa lấy | Nó chắc chắn không có trong classpath |
| Có một array class trong `loaded` | JVM đã có class đại diện kiểu mảng đó | Có thể chèn bytecode vào chính array class |
| Có hidden class trong `loaded` | Runtime có một hidden class đang được quan sát | Có thể tìm class này bằng binary name hoặc sửa như class thường |
| Có class từ bootstrap loader | Class được nạp ở loader đó | Mọi class bootstrap đều không thể sửa |
| Có class thuộc named module | Class có module metadata | Module graph đã cho phép mọi helper/transformer tùy ý truy cập |

Một snapshot có thể thay đổi giữa hai lần gọi vì các thread khác đang nạp class, sử dụng `MethodHandles.Lookup.defineHiddenClass`, sinh proxy hoặc vì class loader/hidden class được dọn khi không còn tham chiếu. **Không sử dụng số lượng class như một sổ cái bất biến.**

### Loaded khác Initialized

JVM tách **loading**, **linking** và **initialization**. Một `Class<?>` nằm trong danh sách loaded không chứng minh static initializer của nó đã chạy hay method nghiệp vụ từng được gọi. Việc khảo sát không nên chủ động “thử gọi class” để xác nhận nếu điều đó có thể kích hoạt side effects.

Chẳng hạn:

```java
Class<?> c = Class.forName("com.example.Target", false, loader);
```

`initialize=false` không yêu cầu khởi tạo class, nhưng **vẫn có thể tải class** nếu nó chưa tồn tại, làm thay đổi chính đối tượng khảo sát. Nếu mục tiêu chỉ là **lấy danh sách đã nạp**, ưu tiên đọc snapshot `getAllLoadedClasses()` thay vì cố nạp mọi tên class từ classpath.

## 3. `getInitiatedClasses(loader)` không giống `getAllLoadedClasses()`

Chữ ký:

```java
Class<?>[] classes = instrumentation.getInitiatedClasses(loader);
```

`getInitiatedClasses` trả về các class mà loader đã được ghi nhận là **initiating loader** — loader có thể tìm class theo tên qua class loading, `Class.forName` hoặc bytecode linkage. Nếu `loader == null`, nó nói về bootstrap loader.

Điều này **không đồng nghĩa** “các class có `getClassLoader()==loader`” trong mọi trường hợp. Một loader con có thể **delegate** lên loader cha để tìm một class, nên initiating loader và defining loader không nhất thiết trùng nhau.

Các khác biệt quan trọng:

| API | Phạm vi | Điểm cần chú ý |
| --- | --- | --- |
| `getAllLoadedClasses()` | Toàn JVM tại lần lấy snapshot | Có thể bao gồm hidden classes và array classes |
| `getInitiatedClasses(loader)` | Các class mà loader được ghi nhận có thể tìm theo tên | Không bao gồm hidden class/interface và array có thành phần hidden |
| `clazz.getClassLoader()` | **Defining loader** của class | `null` biểu thị bootstrap loader |
| `clazz.getModule()` | Module chứa class | Không thể thay cho kiểm tra modifiability |
| `clazz.getName()` | Tên class cho hiển thị/lọc sơ bộ | Có thể đặc biệt với array/hidden class; không đủ phân biệt class identity |

Một class có cùng binary name nhưng được **hai defining loader khác nhau** nạp có thể là hai runtime types khác nhau. Muốn sửa đúng class, phải sử dụng **đúng đối tượng `Class<?>`**, không chỉ giữ một chuỗi tên và đoán lại loader về sau.

### Tình huống dễ sai

Bạn gọi `getInitiatedClasses(webappLoader)` rồi nhìn thấy một class JDK. Điều đó **không** chứng minh `webappLoader` tự định nghĩa class JDK ấy; loader có thể delegate tới bootstrap. Nếu muốn loại trừ class được định nghĩa bởi bootstrap, hãy kiểm tra `clazz.getClassLoader()` thay vì chỉ dựa vào việc class xuất hiện trong initiated list.

Nếu đang tìm class một webapp để instrument, nên kết hợp **binary name + defining loader + module + trạng thái modifiable**, chứ không lấy class có tên trùng đầu tiên trong snapshot.

## 4. `isModifiableClass(clazz)` kiểm tra điều gì?

Chữ ký:

```java
boolean modifiable = instrumentation.isModifiableClass(clazz);
```

Theo Javadoc JDK 17, method trả `true` nếu class được JVM coi là **có thể sửa định nghĩa** bằng redefinition/retransformation, trả `false` nếu class không modifiable. Nó hỏi về **class cụ thể**, không về khả năng của toàn JVM.

Các điều được JDK quy định rõ:

- **Primitive classes** như `int.class`, `boolean.class`, `void.class` là **không modifiable**.
- **Array classes** như `String[].class`, `int[].class` hoặc `OrderService[][]` là **không modifiable**.
- Một số class **do triển khai JVM quyết định** cũng có thể không modifiable.
- `isModifiableClass(null)` ném `NullPointerException`.
- Giá trị trả về **không bị thay đổi** chỉ vì `isRetransformClassesSupported()` hoặc `isRedefineClassesSupported()` bật/tắt; phải kiểm tra các capability ấy riêng.

Đây là một nguồn nhầm lẫn lớn: một class có thể trả `true` ở `isModifiableClass` **dù agent hiện tại không có quyền gọi** `retransformClasses` hoặc `redefineClasses`.

### Vì sao array class có thể được liệt kê nhưng không thể sửa?

JVM tạo class đại diện kiểu mảng bằng cơ chế riêng; nó không có một ordinary `.class` file với method body của ứng dụng để thay như class thường. Nếu ứng dụng dùng `OrderService[]`, bạn có thể instrument logic thao tác mảng ở các method ứng dụng hoặc dùng loại công cụ khác, nhưng **không thể truyền chính `OrderService[].class` cho `retransformClasses`** để chèn method.

```java
// Với Instrumentation inst đã được agent cấp:
System.out.println(inst.isModifiableClass(String[].class)); // false
System.out.println(inst.isModifiableClass(int[].class));    // false
System.out.println(inst.isModifiableClass(int.class));      // false
```

Đây là đoạn minh họa trong agent, không có `main` độc lập. `String.class` **khác `String[].class`**; không suy ra class thường `String` luôn modifiable hay luôn không modifiable từ quy tắc dành cho array.

### Hidden classes và generated classes

JDK 17 có `Class.isHidden()`. Hidden class thường được tạo bằng `MethodHandles.Lookup.defineHiddenClass(...)`, có thể dùng trong hạ tầng runtime hoặc một số chiến lược sinh lambda/proxy. `getAllLoadedClasses()` **có thể chứa chúng**, nhưng `getInitiatedClasses(loader)` **không chứa hidden classes**, vì chúng không được tìm theo tên qua loader theo cách class thông thường.

Ở HotSpot/JVMTI hiện đại, hidden classes không phải đối tượng được phép redefine/retransform theo cơ chế class thường. Dù vậy, **không nên dự đoán chỉ từ tên class**: hãy xem `isHidden()`, `isArray()` và giá trị chính thức từ `isModifiableClass` cho đối tượng thực tế, không dùng regex loại trừ “tên chứa `/0x`” rồi coi đó là hợp đồng API.

Khi instrumentation target là lambda, một số class có thể là hidden/generated theo triển khai. Đừng giả định có thể liệt kê rồi sửa từng lớp lambda như class nghiệp vụ. Thay vào đó, xét instrument **class/method ở nơi lambda được tạo hoặc gọi** và các hook thích hợp cho runtime.

## 5. Ba điều kiện riêng: class, capability và tính hợp lệ của thay đổi

Bảng phân tách:

| Câu hỏi | API/chứng cứ | Điều nó **không** bảo đảm |
| --- | --- | --- |
| Class đang được liệt kê? | Có trong `getAllLoadedClasses()` | Modifiable, đã instrument, đã initialize |
| Class modifiable? | `isModifiableClass(clazz)` | Agent có capability hoặc bản bytes mới hợp lệ |
| JVM/agent cho retransform? | `isRetransformClassesSupported()` | Mọi class đều modifiable |
| JVM/agent cho redefine? | `isRedefineClassesSupported()` | Có class bytes mới hợp lệ, schema tương thích |
| Update đã thực hiện? | Lời gọi API trả bình thường, runtime QA | Business logic đúng nếu chưa test |
| Transformer có tham gia? | Callback/log của `ClassFileTransformer` | JVM đã cài đặt output cuối thành công |

Đối với **retransformation**:

```java
if (instrumentation.isRetransformClassesSupported()
        && instrumentation.isModifiableClass(target)) {
    instrumentation.retransformClasses(target);
}
```

Đoạn này là **mẫu điều kiện**, không phải chương trình tự chạy; vẫn phải bảo đảm `target` đúng class, transformer chain hợp lệ và xử lý checked exception. Nếu một class được liệt kê nhưng `isModifiableClass` là `false`, không nên cố retransform chỉ để xem nó có ném lỗi hay không.

Đối với **redefinition**:

```java
if (instrumentation.isRedefineClassesSupported()
        && instrumentation.isModifiableClass(target)) {
    instrumentation.redefineClasses(
            new java.lang.instrument.ClassDefinition(target, replacement));
}
```

`replacement` phải là `byte[]` chứa **class file hoàn chỉnh, hợp lệ và tương thích schema**; chưa được định nghĩa trong đoạn mã minh họa này. `redefineClasses` không lấy path hoặc bản patch; nó nhận `ClassDefinition` với class đang tồn tại và bytes thay thế.

### Manifest và capability

Agent JAR có thể chứa:

```text
Manifest-Version: 1.0
Premain-Class: demo.survey.SurveyAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

```

Hai flag yêu cầu JVM cung cấp khả năng tương ứng **nếu JVM hỗ trợ**. Nếu một flag không khai báo là `true`, capability đó không được bật chỉ nhờ có agent. `isModifiableClass` **không** được dùng thay cho hai phép hỏi capability.

Lab ở mục 8 dùng manifest này để khảo sát hai flag, **nhưng tuyệt đối không thực hiện redefine hoặc retransform**. Trên HotSpot/OpenJDK JDK 17 thông dụng, cả hai thường `true`; trên runtime khác có thể `false`, nên kết quả phải đọc đúng thực tế.

## 6. Đừng nhầm modifiable với “sửa bất kỳ bytes nào cũng được”

Một class có `isModifiableClass(clazz)==true` vẫn phải tuân theo các giới hạn khi cập nhật định nghĩa:

- Không tự do thêm/xóa/đổi tên field hoặc method trong một lần redefine/retransform thông thường.
- Không đổi method descriptors, modifiers, superclass, interfaces hay những structural attributes bị cấm như `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses`.
- Method bodies và một số constant-pool/attribute updates có thể được phép **nếu** output hợp lệ và JVM hỗ trợ.
- Bytecode phải qua verifier; stack-map frames, branch offsets và exception table phải nhất quán.
- Method helper do agent chèn phải được đúng class loader/module tìm thấy và có quyền truy cập.
- Một transformer khác trong chain có thể làm bytes cuối thay đổi; agent của bạn không độc quyền output JVM nhận.
- Nếu phép update trả lỗi, không class nào trong yêu cầu được cài đặt định nghĩa mới thành công theo hợp đồng API, dù các callback có thể đã log hoặc cập nhật counter trước đó.

Do vậy:

```text
listed = true
modifiable = true
capability = true
```

mới là điều kiện **có thể bắt đầu thử cập nhật**, không phải bằng chứng **cập nhật chắc chắn thành công**.

**Không dùng việc `ClassFileTransformer.transform(...)` được gọi làm bằng chứng class đã được sửa.** Transformer có thể trả `null`; hoặc trả bytes lỗi; hoặc JVM không cài bytes sau khi kiểm tra. Phải xác nhận thao tác hoàn tất thành công rồi chạy runtime tests.

### Redefinition và retransformation tác động phiên bản method ra sao?

Khi cập nhật thành công, những **active stack frames** của method cũ có thể tiếp tục chạy bytecode cũ; các invocation mới dùng method version mới. JVM không tự chạy lại class initializer hoặc reset static fields do các thao tác đó. Các instance đang tồn tại vẫn tồn tại. Những giới hạn này liên quan runtime behavior, không ảnh hưởng tiêu chí ban đầu về việc class có nằm trong snapshot hay không.

## 7. Một quy trình chọn candidate an toàn

Thay vì duyệt mọi `Class<?>` rồi cố retransform hết, hãy dùng nhiều tầng lọc theo ý định:

```text
1. Nạp danh sách từ getAllLoadedClasses().
2. Xác định tên package/class cần được quan sát.
3. Kiểm tra defining class loader và module.
4. Loại array, primitive, hidden classes không thuộc kế hoạch.
5. Chỉ giữ Class<?> có isModifiableClass == true.
6. Xác nhận JVM/agent capability cho thao tác dự định.
7. Kiểm tra lớp và version đã được agent transform trước đó?
8. Kiểm soát số class, rate, thứ tự và phạm vi update.
9. Chạy retransform/redefine trong môi trường an toàn khi được phép.
10. Verify kết quả API, probe semantics và chi phí runtime.
```

Đây là **các bước kiểm tra**, không phải lời khuyên biến một agent khảo sát thành agent tự động sửa toàn JVM.

### Filter bằng package name chưa đủ

Ví dụ dùng trong agent:

```java
// Ký hiệu minh họa; inst, targetLoader đã được khai báo.
for (Class<?> clazz : inst.getAllLoadedClasses()) {
    if (clazz.isPrimitive() || clazz.isArray() || clazz.isHidden()) {
        continue;
    }
    if (clazz.getClassLoader() != targetLoader) {
        continue;
    }
    if (!clazz.getName().startsWith("com.example.orders.")) {
        continue;
    }
    if (!inst.isModifiableClass(clazz)) {
        continue;
    }
    // Đây mới là candidate; CHƯA gọi retransform/redefine.
}
```

**Tại sao so loader bằng identity?** Cùng tên class ở hai loader là hai đối tượng runtime khác nhau. Đừng lấy `clazz.getName().equals("com.example.Order")` làm điều kiện duy nhất cho thao tác có side effects.

**Tại sao không lọc `java.*` bằng một luật “tất cả không modifiable”?** Javadoc không nói mọi class Java core đều không modifiable. Có class JVM sẽ cho sửa, nhưng điều đó không có nghĩa bạn **nên** sửa chúng. Dùng policy allowlist/denylist và mức độ rủi ro riêng, không gộp “không muốn sửa” với “JVM không cho sửa”.

### `Class<?>` từ snapshot có phải là một tham chiếu an toàn?

Trong lúc snapshot và xử lý, class loader hoặc chính sách runtime có thể thay đổi. `Class<?>` là object đại diện class, nhưng việc giữ nó trong agent lâu dài (ví dụ static map với key `Class<?>`) có thể vô tình giữ defining class loader sống qua redeploy. Khảo sát nên dùng dữ liệu tóm tắt **có kiểm soát** và không giữ tham chiếu mạnh tới hàng nghìn plugin classes nếu không thật sự cần.

Ngoài ra, `isModifiableClass` và capability là **preflight**, không thay thế việc xử lý lỗi khi API cập nhật thật sự chạy. Một candidate có thể gặp thay đổi môi trường, xung đột transformer khác hoặc lỗi bytes lúc cài.

## 8. Lab Java 17+ độc lập: khảo sát rồi không sửa class nào

Bài lab này sử dụng một startup Java agent nhận `Instrumentation`, sau đó application chủ động yêu cầu khảo sát **một class thường và một array class**. Nó chứng minh:

1. Class thường và array class **đã được JVM nạp** có thể cùng nằm trong `getAllLoadedClasses`.
2. Array class **không modifiable**, dù có mặt trong snapshot.
3. Primitive `int.class` **không modifiable** (không yêu cầu primitive phải xuất hiện trong snapshot).
4. Modifiability của class thường được kiểm tra **riêng** và có thể phụ thuộc JVM.
5. Khả năng retransform và redefine được hỏi **bằng hai flag khác**, không suy ra từ modifiability.
6. Code **không hề gọi** `retransformClasses` hoặc `redefineClasses`, nên đây là survey-only agent.

### 8.1. Cấu trúc file

```text
loaded-vs-modifiable/
├── agent.mf
├── agent-src/demo/survey/SurveyAgent.java
└── app-src/demo/survey/
    ├── Main.java
    └── Observed.java
```

Sau build có `out/agent`, `out/app`, `out/survey-agent.jar`. JAR agent được tạo từ `out/agent` và app được compile vào `out/app`. Không cần ASM/Byte Buddy, không có thư viện ngoài JDK.

### 8.2. `agent-src/demo/survey/SurveyAgent.java`

```java
package demo.survey;

import java.lang.instrument.Instrumentation;
import java.util.Arrays;

public final class SurveyAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agent: ready");
    }

    private static boolean contains(
            Class<?>[] classes, Class<?> target) {
        return Arrays.asList(classes).contains(target);
    }

    public static void survey(
            Class<?> ordinary, Class<?> arrayType) {

        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("No Java agent installed");
        }

        // Lấy snapshot duy nhất sau khi app đã tạo hai Class objects.
        Class<?>[] loaded = inst.getAllLoadedClasses();

        System.out.println(
                "survey: ordinary-listed=" + contains(loaded, ordinary));
        System.out.println(
                "survey: array-listed=" + contains(loaded, arrayType));

        ClassLoader loader = ordinary.getClassLoader();
        Class<?>[] initiated = inst.getInitiatedClasses(loader);
        System.out.println(
                "survey: ordinary-initiated=" +
                contains(initiated, ordinary));

        boolean ordinaryModifiable = inst.isModifiableClass(ordinary);
        System.out.println(
                "survey: ordinary-modifiable=" + ordinaryModifiable);
        System.out.println(
                "survey: array-modifiable=" +
                inst.isModifiableClass(arrayType));
        System.out.println(
                "survey: primitive-modifiable=" +
                inst.isModifiableClass(int.class));

        boolean canRetransform = inst.isRetransformClassesSupported();
        boolean canRedefine = inst.isRedefineClassesSupported();
        System.out.println(
                "survey: retransform-supported=" + canRetransform);
        System.out.println(
                "survey: redefine-supported=" + canRedefine);

        boolean candidate = ordinaryModifiable && canRetransform;
        System.out.println(
                "survey: retransform-candidate=" + candidate);

        // Cố ý KHÔNG gọi retransformClasses/redefineClasses.
        System.out.println("survey: mutation-performed=false");
    }
}
```

**Giải thích kỹ:**

- `premain` chạy từ agent JAR, lưu `Instrumentation` do JVM cấp. Đây không phải object có thể tự `new Instrumentation()`.
- App sẽ gọi `SurveyAgent.survey(...)`; vì vậy app cần nhìn thấy class agent qua classpath được hướng dẫn.
- `Arrays.asList(classes).contains(target)` kiểm tra **object `Class<?>` tương ứng**, không dựa vào chuỗi tên đơn thuần.
- `getAllLoadedClasses` được gọi **sau khi app đã lấy `Observed.class` và tạo array class**, nên bài lab có bằng chứng hai loại class tồn tại.
- `getInitiatedClasses(loader)` là phép khảo sát bổ sung: class thông thường được loader app tìm bằng tên. Nó không được dùng như danh sách toàn JVM.
- `isModifiableClass` được gọi trên class thường, array và primitive. Hai loại cuối có giá trị `false` **theo đặc tả**.
- Hai capability được hỏi riêng. Với `Can-Retransform-Classes` và `Can-Redefine-Classes` trong manifest, HotSpot/OpenJDK thông thường trả `true`; JVM khác có thể không hỗ trợ.
- `candidate` là **“được phép cân nhắc”** cho retransform, không phải “đã retransform”.
- Không đăng ký transformer và không thay bytecode; bài này chứng minh **khảo sát và phân loại**, không phải chèn probe.

### 8.3. `app-src/demo/survey/Observed.java`

```java
package demo.survey;

public final class Observed {
    public int value() {
        return 42;
    }
}
```

Đây là class ứng dụng thường, có instance method đơn giản. Không có nhu cầu initialize hoặc invoke method để khảo sát modifiability; việc tham chiếu `Observed.class` đủ để JVM có class object sau quá trình load/resolve.

### 8.4. `app-src/demo/survey/Main.java`

```java
package demo.survey;

import java.lang.reflect.Array;

public final class Main {
    public static void main(String[] args) {
        Class<?> ordinary = Observed.class;

        // Bảo đảm JVM đã tạo class đại diện mảng Observed[].
        Class<?> arrayType =
                Array.newInstance(ordinary, 0).getClass();

        SurveyAgent.survey(ordinary, arrayType);
    }
}
```

`Array.newInstance(ordinary, 0)` tạo **mảng độ dài 0**; lấy `getClass()` để thấy class mảng. Không cần tạo một phần tử `Observed` nào. Đừng chỉ giả định `Observed[].class` có trong snapshot trước lúc JVM tạo array class; lab chủ động kích hoạt điều kiện đó.

### 8.5. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.survey.SurveyAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

```

Hai capability được khai báo để **khảo sát** trạng thái hỗ trợ; không có lệnh nào dùng chúng để sửa class. Giữ một dòng trống cuối manifest. JVM có quyền báo capability `false` nếu không hỗ trợ. Không nên thử thay đổi class chỉ vì có flag `true`.

### 8.6. Biên dịch và chạy bằng Bash (Linux/macOS/Git Bash)

Trong thư mục `loaded-vs-modifiable`:

```bash
mkdir -p out/agent out/app

javac -encoding UTF-8 -d out/agent \
    agent-src/demo/survey/SurveyAgent.java

jar --create --file out/survey-agent.jar \
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/agent -d out/app \
    app-src/demo/survey/Observed.java \
    app-src/demo/survey/Main.java

java -javaagent:out/survey-agent.jar \
    -cp out/agent:out/app demo.survey.Main
```

Classpath chứa `out/agent` vì `Main` gọi `SurveyAgent.survey(...)`. Đây là cấu hình lab đơn giản; agent production thường không cho application gọi trực tiếp implementation agent mà cung cấp API bridge riêng nếu cần. Trên Unix-like systems, nhiều classpath entries phân tách bằng dấu `:`.

### 8.7. Biên dịch và chạy bằng PowerShell (Windows)

```powershell
New-Item -ItemType Directory -Force `
    -Path out/agent, out/app | Out-Null

javac -encoding UTF-8 -d out/agent `
    agent-src/demo/survey/SurveyAgent.java

jar --create --file out/survey-agent.jar `
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/agent -d out/app `
    app-src/demo/survey/Observed.java `
    app-src/demo/survey/Main.java

java -javaagent:out/survey-agent.jar `
    -cp "out/agent;out/app" demo.survey.Main
```

PowerShell sử dụng backtick để nối dòng và classpath nhiều entry phân tách bằng `;`. Lệnh `javac`/`jar`/`java` cần thuộc JDK 17+ tương thích. Nếu agent JAR thiếu `Premain-Class`, JVM không gọi `premain` được và lab sẽ lỗi; kiểm tra manifest trước.

### 8.8. Stdout dự kiến và cách đọc đúng

Trong **HotSpot/OpenJDK JDK 17+ thông dụng** có hỗ trợ cả hai capability:

```text
agent: ready
survey: ordinary-listed=true
survey: array-listed=true
survey: ordinary-initiated=true
survey: ordinary-modifiable=true
survey: array-modifiable=false
survey: primitive-modifiable=false
survey: retransform-supported=true
survey: redefine-supported=true
survey: retransform-candidate=true
survey: mutation-performed=false
```

**Giá trị không được cam kết giống nhau trên mọi JVM:** `ordinary-modifiable`, `retransform-supported`, `redefine-supported` và `retransform-candidate` có thể là `false` trên một runtime khác. Đó không phải lỗi thí nghiệm; chính kết quả khác nhau chứng minh vì sao cần hỏi JVM, không suy từ việc class xuất hiện. Những dòng `array-modifiable=false`, `primitive-modifiable=false` là quy tắc API ổn định.

`ordinary-listed=true` và `array-listed=true` được kỳ vọng vì code chủ động đưa cả hai class vào trạng thái loaded trước snapshot; môi trường tùy biến có thể có lifecycle đặc thù nhưng logic của bài lab được thiết kế rõ ràng. `ordinary-initiated=true` đúng với system/application loader trong bố trí classpath này.

**Một dòng quyết định rất quan trọng:** `survey: mutation-performed=false`. Ngay cả khi `retransform-candidate=true`, ta vẫn **chưa thực hiện** bất kỳ phép sửa nào. Việc in `modifiable=true` không phải audit record rằng một class đã được instrument.

## 9. Thử nghiệm đối chứng: hiện ra trong list nhưng bị loại

### A. Array class

Lấy `String[].class` hoặc `Observed[].class` rồi gọi `inst.isModifiableClass(...)`. Giá trị là `false` theo JDK. Không gọi `retransformClasses` trên array class để tạo lỗi không cần thiết; đã có cách kiểm tra trực tiếp.

### B. Primitive class

`int.class`, `long.class`, `boolean.class`, `void.class` đều không modifiable. **Không cần** chứng minh những primitive `Class` này có trong `getAllLoadedClasses()`. Javadoc của loaded list nêu lớp/interface và arrays; bản thân việc có một `Class` đại diện primitive không phải bằng chứng mọi primitive xuất hiện trong snapshot.

### C. Hidden class

Nếu trong JVM có hidden class từ `Lookup.defineHiddenClass`, `getAllLoadedClasses` có thể liệt kê nó; `getInitiatedClasses(loader)` không liệt kê loại này. Phân loại theo `Class.isHidden()`, sau đó hỏi `isModifiableClass`. Trên HotSpot/JVMTI, hidden classes không được retransform/redefine như class thông thường. Không cố tìm theo tên ngẫu nhiên có suffix hoặc giữ strong reference vô hạn chỉ để quan sát một hidden class.

### D. Class ứng dụng bình thường nhưng capability bị tắt

Tạm tạo một **bản manifest riêng** bỏ `Can-Retransform-Classes: true` và `Can-Redefine-Classes: true`, đóng gói lại agent JAR rồi chạy **JVM mới**. Hai phép `is*Supported()` sẽ phản ánh capability agent không yêu cầu. `isModifiableClass(Observed.class)` có thể vẫn báo `true`, bởi Javadoc nói **giá trị này độc lập với hai flag**. Khi đó `retransform-candidate` là `false`, dù class vẫn listed và modifiable.

Đây là thử nghiệm rất tốt để tách **“class có thể sửa về mặt loại/VM”** khỏi **“agent hiện có permission/capability để sửa”**. Đừng sửa manifest ngay trong lần JVM đã chạy rồi mong capability được cập nhật động.

### E. Class cùng tên từ nhiều loader

Giả sử hai plugin loaders tự định nghĩa `com.example.Plugin`. Snapshot có thể chứa **hai `Class<?>` khác nhau** với `getName()` giống nhau. Nếu chọn theo `name` mà không kiểm tra loader/module, agent có thể sửa nhầm plugin hoặc phá dữ liệu tenant khác.

Để xác định chính xác, dùng object identity và log defining loader, module/layer khi cần. Không chỉ dùng `Class.forName(name)` không kèm loader, bởi nó có thể load/class-resolve qua **loader khác**.

### F. Có trong snapshot nhưng không từng qua transformer của agent

Một agent gắn vào JVM sau khi class đã load có thể nhìn thấy class ấy trong `getAllLoadedClasses`. Nhưng `getAllLoadedClasses` **không** thông báo rằng transformer của agent đã được gọi trước đây. Nếu transformer được đăng ký **sau** thời điểm load, nó không tự nhận lại class-load event cũ.

Cần capability thích hợp và chủ động `retransformClasses`/`redefineClasses` nếu muốn xử lý class đã nạp, trong giới hạn JVM và khi được phép. Việc liệt kê không tự kích hoạt callback.

## 10. Những câu hỏi khi chuẩn bị sửa class đã nạp

Thay vì viết một vòng lặp “for each loaded class, retransform”, hãy ghi rõ:

- **Mục tiêu:** Vì sao cần biến đổi lớp này? Có dùng JFR/metrics/quan sát không xâm lấn thay được không?
- **Định danh:** Binary name, defining loader, module; có hai bản class trùng tên không?
- **Loại class:** Array, primitive, hidden, generated, JDK internals, class của agent?
- **Class đã nạp:** Có trong snapshot tại thời điểm nào?
- **Modifiability:** `inst.isModifiableClass(target)` trả gì trên **JVM thật**?
- **Capability:** Muốn retransform hay redefine? Cờ hỗ trợ tương ứng có `true` không?
- **Policy:** Agent có được phép sửa class này hay chỉ được đo? Có allowlist/denylist và giới hạn tenant không?
- **Bytes:** Có transformer/bytecode generator tạo classfile hợp lệ, đúng version/schema không?
- **Chain:** Có agent Java/JVMTI khác đã đăng ký cùng class? Thứ tự biến đổi và kết quả `null` ra sao?
- **Rollback:** Nếu logic mới sai, có bản bytes cũ và lộ trình rollback hợp lệ không?
- **Hành vi:** Có test successful return, exception path, concurrency, static state, stack-map frames và helper linkage?
- **Vận hành:** Có giới hạn số class mỗi đợt, timeout, memory/log volume và giám sát lỗi không?

Nếu bất kỳ điều kiện bắt buộc nào chưa đạt, giữ trạng thái **candidate-only** và không gọi API sửa class. Quy trình này giúp agent có thể khám phá hàng chục nghìn class nhưng chỉ biến đổi một tập nhỏ có chủ đích.

## 11. Phân biệt “không modifiable” với “không được phép instrument”

Hai khái niệm có thể trùng trong một số trường hợp nhưng **không tương đương**:

- `isModifiableClass(clazz)==false`: JVM cho biết class này **không sửa định nghĩa được** theo cơ chế tương ứng.
- `isModifiableClass(clazz)==true` nhưng policy `deny`: về kỹ thuật có thể sửa, nhưng **không nên/không được sửa** trong ứng dụng hiện tại.
- `isModifiableClass(clazz)==true`, policy allow nhưng capability false: chưa đủ điều kiện **gọi API**.
- Tất cả true nhưng output class lỗi: JVM vẫn từ chối cập nhật.
- Tất cả true và update thành công: vẫn cần kiểm chứng **business semantics**.

Ví dụ không nên có trong production:

```java
// CÁCH LÀM NGUY HIỂM — đừng chạy:
for (Class<?> c : inst.getAllLoadedClasses()) {
    if (inst.isModifiableClass(c)) {
        inst.retransformClasses(c);
    }
}
```

Đoạn trên chỉ mang tính cảnh báo, không phải bài lab runnable; `inst` là biến chưa được khai báo. Nó có thể kích hoạt hàng nghìn callbacks, làm chậm JVM, đụng helper classes, tăng memory/GC, khiến một số class phát sinh linkage issues và làm thay đổi semantics trong lúc app hoạt động.

**Chiến lược an toàn:** filter theo owner/module/loader, batch nhỏ có kiểm soát, đo overhead trong staging, xử lý errors, không thực hiện mutation trong một thao tác chỉ có mục đích khảo sát.

## 12. Lỗi thường gặp trong runtime survey

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `getAllLoadedClasses` rất nhiều, số candidate ít | Arrays, hidden, JDK internals, policy filter hoặc JVM hạn chế | Phân loại theo type/loader/module, không coi là thiếu sót |
| `isModifiableClass` trả `false` với array | Hợp đồng JDK | Không cố retransform array; instrument method sử dụng mảng |
| Primitive báo unmodifiable | Hợp đồng JDK | Không thử truyền `int.class` cho retransform |
| Class thường báo `true` nhưng `retransformClasses` lỗi | Capability false, bytes/schema không hợp lệ, transformer khác gây lỗi | Kiểm tra global flag và stack trace/exception thật |
| `UnmodifiableClassException` | Class đích không modifiable | Kiểm tra `isModifiableClass` và loại class |
| `UnsupportedOperationException` | JVM/agent không hỗ trợ API hoặc thay đổi schema bị cấm | Kiểm tra manifest/capability và phạm vi thay đổi |
| `ClassFormatError` / `VerifyError` | Transformer sinh class bytes không hợp lệ | Verify bytecode/stackmap/attributes, chạy test trên JVM mục tiêu |
| `NoClassDefFoundError` cho helper | Target loader/module không tìm thấy helper | Cấu hình helper visibility và module access riêng |
| Không tìm thấy class trong initiated list | Nhầm initiating/defining loader hoặc hidden class | Kiểm tra đúng loader và API được dùng |
| Snapshot mới có thêm class | JVM liên tục load class hoặc chính survey làm tải thêm | Gắn timestamp, không diễn giải hai snapshot như delta tuyệt đối |
| Modifiable nhưng không phải class target | Tên tương tự từ plugin/tenant khác | So loader identity, module và allowlist |
| Survey gây heap tăng | Lưu mạnh `Class<?>`/`ClassLoader` của các plugin trong cache | Giới hạn retention, weak references và cleanup |
| Số loaded khác trước/sau attach | Agent và dependency của agent tự nạp thêm class | Ghi rõ thời điểm đo, không so tuyệt đối |
| Instrumentation ngừng hoạt động do crash khi cố sửa mọi class | Mutation scope quá rộng, không kiểm chứng từng class | Tách survey khỏi modification và thử ít lớp |

### Tại sao snapshot count không phải metric độ trễ?

Số class loaded lớn không trực tiếp chứng minh ứng dụng chậm hoặc heap leak. Nó có thể tăng vì class loaders, generated proxies, warmup, dynamic code, frameworks. Muốn kết luận class-loader leak, cần quan sát loader lifecycle, số type sống qua redeploy, retained heap/reference chain, GC và các công cụ profiling thích hợp. **Một lần `getAllLoadedClasses` không chứng minh leak**.

## 13. Chính sách xử lý lỗi khi thực sự cập nhật

Nếu sau khi khảo sát bạn muốn thực hiện retransform/redefine, nên ghi rõ chiến lược:

```text
SURVEY_ONLY
    ↓
TARGET_SELECTED
    ↓
CLASS_MODIFIABLE
    ↓
JVM_CAPABILITY_SUPPORTED
    ↓
TRANSFORMER_POLICY_APPROVED
    ↓
BYTES_VALIDATED (khi cần)
    ↓
API_CALLED
    ├─ exception → FAILED / no installed changes
    └─ returns normally → UPDATE_APPLIED / runtime QA
```

Các trạng thái trên là **mô hình quy trình** chứ không phải enum JDK. Tách `TARGET_SELECTED` khỏi `UPDATE_APPLIED` giúp dashboard và audit logs không đếm nhầm số lượng class đã sửa.

**Exception taxonomy:**

- `UnmodifiableClassException`: mục tiêu không modifiable.
- `UnsupportedOperationException`: thao tác không được JVM hỗ trợ hoặc cố thực hiện thay đổi không cho phép.
- `ClassFormatError`/`UnsupportedClassVersionError`: class bytes định nghĩa mới không được chấp nhận theo định dạng/version.
- `NoClassDefFoundError` hoặc `LinkageError`: tên class/helper/loader/linkage có thể lỗi.
- `NullPointerException`: truyền `null` ở nơi API không chấp nhận.

Một lần kiểm tra `isModifiableClass` trước API không “miễn trừ” các exception khác. Với một yêu cầu chứa nhiều class, có thể cần transaction-like guarantee theo API: nếu yêu cầu thất bại, không class nào của yêu cầu được cài định nghĩa mới. Callback của transformer có thể đã chạy và tạo log/metric side effects; không tự rollback những side effects ấy.

## 14. Hiệu năng và an toàn khi khảo sát JVM lớn

**Không chạy scan vô hạn mỗi request.** `getAllLoadedClasses` tạo mảng tham chiếu với kích thước phụ thuộc số class JVM đang nạp; quét quá thường xuyên gây overhead. Tốt hơn:

1. Chỉ khảo sát lúc cần (startup checkpoint, yêu cầu admin, giai đoạn chẩn đoán).
2. Lọc theo prefix/package, defining loader và module **trước** khi làm logic nặng.
3. Không log một dòng cho **mỗi** class JVM trong production theo mặc định.
4. Tổng hợp số lượng theo các bucket ổn định; tránh class name/loader identity động trong metrics labels có cardinality vô hạn.
5. Không gọi `Class.forName` hàng loạt để tìm class chưa có nếu nhiệm vụ là *đã loaded hay chưa*.
6. Không giữ class objects hay loader references mạnh vô hạn, đặc biệt trong JVM có hot redeploy.
7. Kiểm soát quyền sử dụng agent/attach; không khảo sát JVM của người khác khi không có quyền.
8. Khi cần target chính xác, lưu ổn định metadata đã được cho phép và đối chiếu lại class object ở thời điểm update.
9. Nếu JVM đang rất bận, đo chi phí/độ trễ của chính thao tác khảo sát và tránh làm gián đoạn hot path.
10. Không cung cấp cho một dashboard “modifiable=true” rồi diễn dịch như lời mời sửa mọi JDK class.

Đôi khi một JFR recording, thread dump hoặc thông tin classloader đã đủ trả lời câu hỏi chẩn đoán, không cần Java agent quét liên tục. Chọn mức xâm nhập thấp nhất phù hợp mục tiêu.

## 15. Các hiểu nhầm cần bác bỏ

**1. “Class nằm trong `getAllLoadedClasses` nên chắc chắn retransform được.”**  
Sai. Array và các class đặc biệt có thể được liệt kê nhưng `isModifiableClass=false`; còn phải có capability.

**2. “`isModifiableClass=true` nghĩa là agent hiện tại đã được cấp `Can-Retransform-Classes`.”**  
Sai. Hai giá trị độc lập theo Javadoc. Kiểm tra `isRetransformClassesSupported()` riêng.

**3. “Muốn redefine thì chỉ kiểm tra `isRetransformClassesSupported` là đủ.”**  
Sai. Dùng `isRedefineClassesSupported()` cho `redefineClasses`.

**4. “`getInitiatedClasses(loader)` chính là toàn bộ class do loader định nghĩa.”**  
Sai. Initiating loader không nhất thiết bằng defining loader; parent delegation làm khác biệt.

**5. “Class không có trong snapshot tức class không tồn tại trong JAR.”**  
Sai. Một file `.class` có thể có trên classpath nhưng chưa được nạp.

**6. “`getAllLoadedClasses` chỉ có class thường, không có array/hidden.”**  
Sai ở JDK 17. API có thể trả cả arrays và hidden classes.

**7. “Có tên class là đủ chọn đúng target.”**  
Sai. Class identity còn phụ thuộc defining loader; nhiều plugin có thể dùng cùng binary name.

**8. “Loaded nghĩa là class initializer đã chạy.”**  
Sai. Loading và initialization là các pha khác nhau.

**9. “`Class.forName` giúp khảo sát mà không làm hệ thống đổi trạng thái.”**  
Không luôn đúng. Nó có thể load/initialize class tùy overload và tham số; hãy thận trọng.

**10. “Modifier `public`/`final` quyết định class có modifiable không.”**  
Không thể chỉ dựa vào source modifiers. Phải hỏi `Instrumentation.isModifiableClass` trên JVM thực.

**11. “Mọi class `java.*` đều không thể sửa.”**  
Không phải quy tắc chung của JDK. Nhiều class có thể modifiable nhưng không nên bị agent tự động sửa.

**12. “Log callback của transformer cho biết class đã được cài bytes mới.”**  
Sai. Callback có thể trả null, hoặc cài đặt thất bại; phải chờ API trả thành công.

**13. “Thay class body sẽ reset static state hoặc tạo instance mới.”**  
Sai. Redefine/retransform không tự chạy lại initializer; object và static fields tiếp tục tồn tại.

**14. “Hidden class có thể tìm qua `Class.forName` bằng tên `getName()`.”**  
Sai. Hidden classes không được khám phá bằng tên theo cách thông thường; đừng viết heuristic dựa trên suffix.

**15. “Có thể dùng snapshot để kết luận class-loader leak chắc chắn.”**  
Sai. Cần theo dõi class/loader lifecycle, GC và retained references theo thời gian.

## 16. Câu hỏi luyện tập

**Câu 1.** `getAllLoadedClasses()` có trả array class không?  
**Đáp:** Có. Javadoc JDK 17 mô tả array classes thuộc phạm vi liệt kê.

**Câu 2.** Vì sao `String[].class` được liệt kê vẫn không sửa được?  
**Đáp:** Array classes luôn `isModifiableClass=false` theo hợp đồng API.

**Câu 3.** `int.class` có thể sửa bằng `redefineClasses` không?  
**Đáp:** Không. Primitive classes không modifiable.

**Câu 4.** Nếu `isModifiableClass(target)==true` nhưng `isRetransformClassesSupported()==false`, có nên gọi `retransformClasses` không?  
**Đáp:** Không. Capability độc lập; thao tác chưa được hỗ trợ.

**Câu 5.** Khi `isModifiableClass(target)==true` và capability true, update class có chắc thành công không?  
**Đáp:** Không. JVM vẫn cần bytes/transformer chain hợp lệ và thay đổi đúng giới hạn schema.

**Câu 6.** `getInitiatedClasses(loader)` có bao gồm hidden class không?  
**Đáp:** Không. Hidden class không thể được tìm theo tên qua class loader như class thường.

**Câu 7.** Hai `Class<?>` có cùng `getName()` có chắc là cùng type?  
**Đáp:** Không. Defining class loader là một phần của runtime identity.

**Câu 8.** `getAllLoadedClasses` có giúp tìm mọi class file trên classpath chưa load không?  
**Đáp:** Không. Nó chỉ liệt kê class đã loaded tại thời điểm lấy snapshot.

**Câu 9.** Làm sao tránh sửa nhầm class của plugin khác?  
**Đáp:** Xác nhận class object, defining loader/module, package allowlist và chỉ candidate modifiable/capability phù hợp.

**Câu 10.** Một class đã loaded trước khi agent attach có tự động được transformer mới đăng ký xử lý không?  
**Đáp:** Không. Đăng ký transformer không phát lại load event; cần cơ chế cập nhật class đã nạp nếu được hỗ trợ.

**Câu 11.** Vì sao bài lab in `mutation-performed=false` ngay cả khi class thường modifiable?  
**Đáp:** Vì chỉ khảo sát. Không gọi API sửa định nghĩa nào.

**Câu 12.** `Class.isHidden()` có thay thế `isModifiableClass` không?  
**Đáp:** Không. Nó chỉ phân loại hidden status; phép hỏi modifiability chính thức dành cho class cụ thể vẫn cần được dùng.

**Câu 13.** Tại sao `getInitiatedClasses` cần phân biệt với `clazz.getClassLoader()`?  
**Đáp:** Một initiating loader có thể delegate đến defining loader khác; hai khái niệm có mục đích khác.

**Câu 14.** Nếu một lần retransform nhiều class thất bại, có được đếm mỗi callback như một class updated không?  
**Đáp:** Không. Callback không xác nhận install; API failure không cài định nghĩa mới của tập đã yêu cầu.

**Câu 15.** Vì sao khảo sát class loader của ứng dụng có thể tăng memory nếu agent lưu mãi các `Class<?>` tìm được?  
**Đáp:** Tham chiếu mạnh tới class có thể giữ defining loader và các class/objects liên quan sống qua redeploy, gây leak.

## 17. Tài liệu chuẩn và cách tra cứu

- [JDK 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): nguồn chính cho `getAllLoadedClasses`, `getInitiatedClasses`, `isModifiableClass`, capability retransform/redefine và giới hạn API.
- [JDK 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): cơ chế nhận `Instrumentation` ở `premain`/`agentmain`, manifest capability và phạm vi Java agent.
- [JDK 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback biến đổi class load/redefine/retransform và điều kiện trả bytes.
- [JDK 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isArray`, `isPrimitive`, `isHidden`, `getClassLoader`, `getModule`.
- [JDK 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining/initiating loader, delegation và class lookup.
- [JVM Tool Interface (JVMTI) JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html): `GetLoadedClasses`, `IsModifiableClass`, `RetransformClasses`, `RedefineClasses` và giới hạn lớp đặc biệt.
- [JVMS 17 — Loading, Linking and Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity, loader constraints và các pha của JVM.

**Ghi nhớ:** `getAllLoadedClasses()` là **snapshot khám phá**, không phải danh sách các class “an toàn để sửa”. `isModifiableClass()` là câu trả lời về **từng class**, độc lập với `isRetransformClassesSupported()`/`isRedefineClassesSupported()`. Chỉ khi đã xác nhận đúng `Class<?>` theo loader/module, kiểm tra capability, policy, schema, bytes và runtime QA, mới có thể chuyển từ **listed** sang một thay đổi bytecode được thực hiện có kiểm soát.