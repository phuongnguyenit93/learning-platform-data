# Bridge method và `Method.isBridge()` trong Java Reflection

## 1. Bridge method là gì và tại sao cần quan tâm?

**Bridge method** là phương thức bổ sung do trình biên dịch Java tạo ra trong một số trường hợp để giữ đúng quy tắc ghi đè phương thức (overriding) ở mức mã máy ảo JVM. Nó đặc biệt xuất hiện khi **generic type erasure** làm chữ ký bytecode của phương thức ở lớp con khác với chữ ký mà mã đã biên dịch hoặc interface gốc cần gọi, và khi **covariant return type** làm kiểu trả về của phương thức ghi đè trở nên cụ thể hơn.

Từ mã nguồn Java, ta chỉ thấy phương thức do lập trình viên khai báo. Nhưng ở runtime, Java Reflection có thể nhìn thấy **cả phương thức thật lẫn bridge method do compiler sinh**. Nếu không nhận diện đúng, công cụ quét API có thể hiển thị hai phương thức tưởng như trùng nhau, bộ lọc annotation có thể xử lý sai, hoặc framework chọn nhầm phương thức để phản chiếu.

Phương thức `java.lang.reflect.Method.isBridge()` cho biết một `Method` có được đánh dấu là **bridge method** hay không. Đây là một **cờ của phương thức**, vì vậy nội dung này thuộc nhóm học về *Modifier và cờ* trong Reflection.

**Kết quả học tập:** hiểu lý do bridge tồn tại, nhìn được bridge trong bytecode và Reflection, phân biệt `isBridge()` với `isSynthetic()`, xử lý đúng khi quét phương thức và biết khi nào cần giữ hoặc loại bridge.

## 2. Cơ chế từ Java source đến JVM

Ở cấp độ mã nguồn Java, generic giúp kiểm tra kiểu lúc biên dịch:

```java
interface Sink<T> {
    void accept(T value);
}

class StringSink implements Sink<String> {
    @Override
    public void accept(String value) {
        System.out.println(value);
    }
}
```

Đoạn trên **minh họa**, chưa phải chương trình độc lập vì chưa có phương thức `main`. Người đọc Java thấy một lời cài đặt `accept(String)` hợp lệ của `Sink<String>`.

Nhưng generic trong Java chủ yếu dựa trên **type erasure**. Sau khi xóa biến kiểu không có bound, chữ ký của phương thức khai báo trong `Sink<T>` trở thành:

```text
Sink.accept(T)              -> bytecode descriptor: (Ljava/lang/Object;)V
StringSink.accept(String)    -> bytecode descriptor: (Ljava/lang/String;)V
```

JVM liên kết lời gọi dựa trên tên và descriptor; descriptor của phương thức trong JVM bao gồm các kiểu tham số và kiểu trả về. Vì vậy, chỉ phương thức `accept(String)` không cung cấp đúng entry point `accept(Object)` mà lời gọi thông qua kiểu `Sink` đã biên dịch có thể sử dụng.

Để duy trì hợp đồng ghi đè, `javac` tạo thêm phương thức tương đương về ý tưởng:

```java
// Mã mô phỏng hành vi bridge do javac sinh, KHÔNG được tự khai báo
// song song với accept(String) trong ví dụ để thay compiler.
public void accept(Object value) {
    accept((String) value);
}
```

Bridge chuyển tiếp lời gọi tới phương thức `accept(String)` và chèn phép ép kiểu cần thiết. Bridge giữ tính đa hình của lời gọi qua interface; nó không làm thay đổi ý nghĩa kiểu generic được kiểm tra ở thời điểm biên dịch.

**Lưu ý:** `accept(Object)` ở trên chỉ là cách giải thích chức năng. Trong mã nguồn `StringSink` ta **không viết** phương thức đó. Trình biên dịch phát sinh bridge vào bytecode với cờ `ACC_BRIDGE`, và với `javac` thường thêm cả `ACC_SYNTHETIC`.

### 2.1. Trường hợp thứ hai: kiểu trả về hiệp biến

Java cho phép phương thức ghi đè trả về một subtype của kiểu trả về ở lớp cha:

```java
class Parent {
    public Number read() {
        return 1;
    }
}

class Child extends Parent {
    @Override
    public Integer read() {
        return 2;
    }
}
```

Ở mức source, `read()` là phương thức ghi đè hợp lệ. Nhưng descriptor của JVM chứa **cả kiểu trả về**:

```text
Parent.read()  -> ()Ljava/lang/Number;
Child.read()   -> ()Ljava/lang/Integer;
```

Để lời gọi được liên kết theo descriptor `()Ljava/lang/Number;` vẫn tới phần cài đặt của `Child`, `javac` có thể tạo bridge `Number read()` gọi đến `Integer read()`. Hai phương thức cùng tên và cùng tham số nhưng khác kiểu trả về có thể đồng tồn tại trong bytecode do compiler sinh; **không được khai báo hai phương thức chỉ khác kiểu trả về trong mã nguồn Java thông thường**.

Như vậy, bridge **không chỉ xuất hiện vì generic**. Khi phân tích Reflection, hãy xét cả quan hệ ghi đè với kiểu trả về hiệp biến.

## 3. Các API và cờ liên quan

| API / thành phần | Ý nghĩa |
| --- | --- |
| `Method.isBridge()` | `true` khi phương thức mang thuộc tính bridge; đây là API Reflection trực tiếp để nhận diện bridge. |
| `Method.isSynthetic()` | `true` khi phương thức được đánh dấu synthetic (không xuất hiện như một khai báo nguồn thông thường); synthetic **không đồng nghĩa** bridge. |
| `Method.getModifiers()` | Lấy tập bit modifier của phương thức; nên dùng `isBridge()` để hỏi riêng về bridge. |
| `Class.getDeclaredMethods()` | Liệt kê các phương thức khai báo trong chính kiểu, bao gồm cả bridge do compiler sinh; không tự bao gồm phương thức chỉ được kế thừa. |
| `Class.getMethods()` | Liệt kê các phương thức `public` nhìn thấy trên kiểu, bao gồm phương thức được kế thừa; có thể chứa bridge phù hợp điều kiện. |
| `Method.getParameterTypes()` / `getReturnType()` | Đọc kiểu runtime của tham số/giá trị trả về, hữu ích để so sánh bridge và phương thức đích. |
| `Method.getGenericParameterTypes()` / `getGenericReturnType()` | Đọc metadata kiểu generic được biểu diễn bởi `Type`; cần hiểu generic và erasure khi phân tích. |
| `javap -p -c -v` | Công cụ JDK xem phương thức, descriptor, cờ `ACC_BRIDGE`/`ACC_SYNTHETIC` và lệnh bytecode. |

Có hai phân biệt quan trọng:

- **Bridge là một loại nhiệm vụ chuyên biệt**: tạo đường chuyển tiếp để bảo toàn ngữ nghĩa ghi đè/liên kết nhị phân sau quá trình biên dịch. **Synthetic là thuộc tính rộng hơn**: compiler có thể sinh các phương thức phụ trợ khác không phải bridge. Vì vậy, điều kiện `isSynthetic()` đơn lẻ **không xác định chính xác** bridge.
- `Modifier` cung cấp các phép hỏi phổ biến như `isPublic`, `isStatic`, `isFinal`, nhưng **không có `Modifier.isBridge(...)`**. Hơn nữa, một số bit class-file có ý nghĩa khác nhau theo loại thành viên: không nên tự giải mã bit của `getModifiers()` bằng những phép kiểm tra vốn dành cho field. Với đối tượng `Method`, sử dụng `method.isBridge()`.

## 4. Ví dụ hoàn chỉnh Java 17+: quan sát bridge bằng Reflection

Lưu mã nguồn sau thành **`BridgeMethodDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class BridgeMethodDemo {
    interface Sink<T> {
        void accept(T value);
    }

    static class StringSink implements Sink<String> {
        @Override
        public void accept(String value) {
            System.out.println("accept(String): " + value);
        }
    }

    static class Parent {
        public Number read() {
            return 1;
        }
    }

    static class Child extends Parent {
        @Override
        public Integer read() {
            return 2;
        }
    }

    private static String signature(Method method) {
        String parameters = Arrays.stream(method.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", "));
        return method.getName() + "(" + parameters + ") -> "
                + method.getReturnType().getSimpleName();
    }

    private static void inspect(Class<?> type, String methodName) {
        System.out.println(type.getSimpleName() + ":");
        Arrays.stream(type.getDeclaredMethods())
                .filter(method -> method.getName().equals(methodName))
                .sorted(Comparator.comparing(BridgeMethodDemo::signature))
                .forEach(method -> System.out.println(
                        "  " + signature(method)
                                + " | bridge=" + method.isBridge()
                                + " | synthetic=" + method.isSynthetic()));
    }

    public static void main(String[] args) throws Exception {
        inspect(StringSink.class, "accept");
        inspect(Child.class, "read");

        Method bridge = StringSink.class.getDeclaredMethod("accept", Object.class);
        System.out.println("invoke accepted:");
        bridge.invoke(new StringSink(), "hello");
        try {
            bridge.invoke(new StringSink(), 42);
        } catch (InvocationTargetException exception) {
            System.out.println("cause: "
                    + exception.getCause().getClass().getSimpleName());
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac --release 17 BridgeMethodDemo.java
java BridgeMethodDemo
```

Kết quả với `javac` và Java 17+:

```text
StringSink:
  accept(Object) -> void | bridge=true | synthetic=true
  accept(String) -> void | bridge=false | synthetic=false
Child:
  read() -> Integer | bridge=false | synthetic=false
  read() -> Number | bridge=true | synthetic=true
invoke accepted:
accept(String): hello
cause: ClassCastException
```

Ví dụ này đã được biên dịch với tùy chọn `--release 17` và chạy trên JDK 21; stdout trên khớp từng dòng.

### 4.1. Phân tích `StringSink`

`getDeclaredMethods()` thấy hai phương thức `accept`:

1. `accept(String)`: phương thức nguồn thật do lập trình viên viết; `isBridge() == false`.
2. `accept(Object)`: bridge của `javac` để tương thích với descriptor đã xóa kiểu của `Sink<T>`; `isBridge() == true` và `isSynthetic() == true`.

Cả hai đều có thể tìm được qua Reflection bằng danh sách kiểu tham số thích hợp:

```java
Method source = StringSink.class.getDeclaredMethod("accept", String.class);
Method bridge = StringSink.class.getDeclaredMethod("accept", Object.class);
```

Đoạn tra cứu này chỉ minh họa, dùng các kiểu `StringSink` và `Method` đã khai báo/import trong chương trình phía trên.

Cách sắp xếp các phương thức bằng `Comparator` trong hàm `inspect` là cố ý: **`Class.getDeclaredMethods()` không đảm bảo thứ tự kết quả**. Không dựa vào vị trí đầu tiên của mảng để kết luận phương thức nào là bridge.

### 4.2. Phân tích `Child`

Ở lớp `Child`, tên và danh sách tham số không giúp phân biệt hai `read()`. Cần xét `getReturnType()` và cờ bridge. Phương thức `read() -> Integer` là phương thức do người dùng khai báo; phương thức `read() -> Number` là bridge do compiler sinh để duy trì liên kết với chữ ký ở `Parent`.

Đừng tự “khử trùng lặp” theo *chỉ* `method.getName()` hoặc tên cộng danh sách tham số khi phân tích các phương thức JVM: như vậy có thể gộp nhầm bridge với phương thức nguồn và đánh mất thông tin quan trọng về descriptor hoặc kiểu trả về.

### 4.3. Vì sao `ClassCastException` xuất hiện?

Gọi:

```java
bridge.invoke(new StringSink(), "hello");
```

là hợp lệ vì tham số runtime của bridge là `Object`; bên trong bridge, giá trị `String` ép kiểu thành công và được chuyển tới `accept(String)`.

Ngược lại, `bridge.invoke(new StringSink(), 42)` vẫn vượt qua bước kiểm tra tham số dạng `Object` của Reflection, nhưng bytecode bridge phải ép `Integer` sang `String`. Phép ép thất bại; `Method.invoke` bao bọc ngoại lệ do phương thức được gọi ném ra trong `InvocationTargetException`. Vì thế đoạn `catch` lấy `exception.getCause()` và in `ClassCastException`.

Đây cũng là lý do **không nên suy luận rằng gọi bridge qua Reflection sẽ an toàn kiểu giống như gọi generic method trong mã nguồn Java đã được biên dịch**.

## 5. Kiểm tra bytecode: xác minh cờ `ACC_BRIDGE`

Sau khi biên dịch `BridgeMethodDemo.java`, chạy:

```bash
javap -p -c -v 'BridgeMethodDemo$StringSink'
javap -p -c -v 'BridgeMethodDemo$Child'
```

Ví dụ lệnh dùng dấu nháy đơn để bảo vệ ký tự `$` trong tên binary của nested class khi chạy bằng shell như PowerShell hoặc Bash. Đọc phần mô tả method và tìm:

- `descriptor: (Ljava/lang/Object;)V` của `accept(Object)`.
- `flags: ... ACC_BRIDGE, ACC_SYNTHETIC` trên bridge do `javac` tạo.
- Lệnh ép kiểu `checkcast java/lang/String` trong bridge và lời gọi tiếp tới `accept:(Ljava/lang/String;)V`.
- Với `Child`, method trả về `Number` được đánh dấu bridge, rồi chuyển tiếp tới method trả về `Integer`.

Lệnh `javap` phục vụ mục tiêu **kiểm chứng biên dịch**, không phải bước bắt buộc khi viết ứng dụng Reflection. Khi cần hỏi một đối tượng `Method`, `isBridge()` dễ đọc và ít phụ thuộc chi tiết biểu diễn bit hơn.

Lưu ý về compiler: ngôn ngữ Java quy định tính tương thích khi ghi đè, nhưng chi tiết cách trình biên dịch sinh bridge, thứ tự các method trong class file và cờ synthetic bổ sung có thể khác theo compiler hoặc công cụ biến đổi bytecode. Vì vậy, đừng đưa giả định “mọi phương thức synthetic đều là bridge” hay “mỗi lớp có đúng một bridge” vào mã dùng chung.

## 6. Chọn phương thức khi quét bằng Reflection

### 6.1. Chỉ hiển thị API do người dùng khai báo

Khi sinh tài liệu hoặc bảng mô tả phương thức dễ đọc từ `getDeclaredMethods()`, thường chỉ muốn hiển thị phương thức chính và loại các đường chuyển tiếp bridge:

```java
Method[] visibleMethods = Arrays.stream(type.getDeclaredMethods())
        .filter(method -> !method.isBridge())
        .toArray(Method[]::new);
```

Đây là **đoạn minh họa**, giả sử có biến `Class<?> type` và import `Method`, `Arrays`; không phải chương trình độc lập. Nếu mục tiêu còn cần bỏ phương thức compiler sinh *khác*, có thể thêm quy tắc `!method.isSynthetic()`, nhưng cần xét ứng dụng có muốn giữ các phương thức synthetic hay không.

Không có một bộ lọc chung đúng cho mọi framework. Công cụ phân tích bytecode, debugger, trình biên dịch, AOP, mô hình gọi động hoặc giải quyết phương thức ghi đè có thể **cần giữ bridge** để hiểu đường dispatch thực tế.

### 6.2. Cần thực thi hoặc ánh xạ một phương thức runtime

Không mặc định rằng mọi bridge chỉ có một phương thức đích đơn giản suy ra bằng tên. Để ánh xạ một bridge tới phương thức nghiệp vụ, có thể phải xét:

- Lớp khai báo và chuỗi lớp cha/interface, không chỉ `getDeclaredMethods()` trên một lớp.
- Danh sách tham số, kiểu trả về và generic type variables sau erasure.
- Quy tắc override, visibility, các phương thức ứng viên và quan hệ covariant return.
- Compiler hoặc thư viện sinh/biến đổi bytecode, khi có.

**Ví dụ quyết định theo mục đích:**

| Nhu cầu | Xử lý bridge |
| --- | --- |
| Sinh tài liệu API người viết khai báo | Thường ẩn `isBridge() == true` để tránh mục lặp. |
| Khảo sát kết quả biên dịch/JVM | Giữ bridge và hiển thị cờ cùng descriptor. |
| Tìm method để xử lý annotation | Xác định method nguồn/đích và chính sách annotation trước khi lọc. |
| Kiểm tra tương thích ghi đè hoặc đường dispatch | Xem bridge là dữ liệu quan trọng. |
| Gọi method qua `Method.invoke` | Kiểm tra chữ ký của method được chọn và ngoại lệ có thể phát sinh trong bridge. |

### 6.3. `getDeclaredMethods()` so với `getMethods()`

`getDeclaredMethods()` tiện để quan sát bridge **sinh trực tiếp trong class đang xét**, kể cả phương thức không public. `getMethods()` chỉ trả về các public method có thể nhìn thấy, kể cả inherited methods, nên phạm vi khác và có thể khiến việc xác định method được khai báo ở đâu kém rõ ràng.

Nếu cần phân biệt bridge của lớp con và phương thức kế thừa, hãy kiểm tra `method.getDeclaringClass()` và phân tích hệ phân cấp lớp/interface. Đừng cho rằng mọi `Method` trả bởi `getMethods()` đều được khai báo trong chính lớp được hỏi.

## 7. Những nhầm lẫn phổ biến

**Nhầm 1 — “Bridge là overload bình thường do người viết định nghĩa”.** Bridge thường không có khai báo nguồn riêng. Nó là một artifact để bảo toàn overriding ở runtime; việc hai entry point xuất hiện khi Reflection không chứng minh lập trình viên chủ ý tạo overload đó.

**Nhầm 2 — “Chỉ generic mới sinh bridge”.** Generic erasure là trường hợp rất thường gặp, nhưng ví dụ `Child.read()` cho thấy covariant return cũng có thể tạo bridge.

**Nhầm 3 — “`isSynthetic()` chính là `isBridge()`”.** Với bytecode do `javac` tạo trong ví dụ, bridge cũng là synthetic. Nhưng synthetic bao gồm các phương thức compiler sinh vì mục đích khác. Hãy hỏi `isBridge()` khi cần biết riêng bridge.

**Nhầm 4 — “Modifier của bridge sẽ hiển thị nhãn bridge”.** `Modifier.toString(method.getModifiers())` không phải API phù hợp để giải thích `ACC_BRIDGE`. Cờ bridge ở JVM có thể dùng giá trị bit trùng với cờ mang nghĩa khác ở loại thành viên khác. Dùng `Method.isBridge()` hoặc kiểm tra `javap -v`.

**Nhầm 5 — “Chỉ cần so tên và tham số là tìm đúng method”.** Bridge của covariant return có thể chỉ khác kiểu trả về ở descriptor. Phải xét `getReturnType()`, cờ bridge và nguồn gốc khai báo.

**Nhầm 6 — “`Method.invoke` qua bridge luôn tương đương gọi method kiểu cụ thể ở source”.** Reflection chấp nhận đối số dựa trên chữ ký runtime được nhìn thấy. Bridge có thể tự ép kiểu và ném `ClassCastException` từ bên trong, như ví dụ `accept(Object)`.

**Nhầm 7 — “Mọi compiler đều sinh đúng cùng một bộ method”.** Sự có mặt, số lượng bridge, cờ synthetic và bytecode chi tiết phụ thuộc quan hệ kiểu và cách compiler phát hành mã. Công cụ xử lý nên kiểm tra metadata thực tế thay vì cố định số lượng method.

## 8. Bài tập tự kiểm tra

1. Thay `Sink<String>` bằng `Sink<Integer>` và viết `IntegerSink.accept(Integer)`. Dự đoán descriptor bridge sau erasure rồi kiểm tra `getDeclaredMethods()` và `isBridge()`.
2. Thử gọi bridge `accept(Object)` bằng một `Integer` trong ví dụ gốc. Giải thích tại sao Reflection nhận tham số `Object` nhưng vẫn có `ClassCastException` từ lời gọi bên trong.
3. Đổi `Parent.read()` và `Child.read()` để trả về các kiểu tham chiếu khác có quan hệ subtype, rồi quan sát bridge với `javap`.
4. Viết bộ lọc hiển thị public API bỏ bridge; sau đó viết chế độ debug giữ bridge và in `getDeclaringClass()`, `getReturnType()`, `isBridge()`, `isSynthetic()`.
5. Tự trả lời: tại sao `!method.isSynthetic()` không đủ để **phân loại** bridge, dù thường loại được bridge do `javac` sinh?

## 9. Ghi nhớ

- **Bridge method** là phương thức chuyển tiếp do compiler sinh nhằm duy trì tương thích overriding/liên kết ở mức bytecode, đặc biệt với generic erasure và covariant return.
- **`Method.isBridge()`** là cách Reflection chuẩn để nhận diện phương thức mang cờ bridge.
- **`isSynthetic()` không đồng nghĩa `isBridge()`**; hai khái niệm mang mục đích khác nhau.
- **`getDeclaredMethods()` có thể trả cả method nguồn lẫn bridge**; luôn kiểm tra cờ trước khi sinh tài liệu hoặc chọn phương thức.
- **Đường dispatch vẫn có thể ép kiểu và ném ngoại lệ**; quan sát được điều đó qua `Method.invoke` và `InvocationTargetException`.
- **Có nên lọc bridge hay không tùy mục đích**: hiển thị API thường lọc, phân tích JVM/override thường giữ.