# Reflection trên đối tượng Class đã có: Hidden class trong Java 15+

## 1. Mục tiêu và phạm vi

**Hidden class** là một lớp được JVM định nghĩa để phục vụ mã sinh ra lúc chạy, chẳng hạn hạ tầng framework và runtime. Tính năng này được chính thức giới thiệu trong **Java 15 (JEP 371)** và vẫn tồn tại trong Java hiện đại. Đặc điểm cốt lõi: hidden class **không có binary name để các lớp khác tham chiếu trực tiếp trong constant pool**, nên không thể tìm nó bằng cách gọi `Class.forName(...)` thông thường.

Tuy nhiên, khi chương trình **đã có một đối tượng `Class<?>` trỏ tới hidden class**, đối tượng đó vẫn hỗ trợ những thao tác reflection quen thuộc: kiểm tra loại lớp, xem constructor, field và method, kiểm tra kiểu của instance và, khi được phép, tạo instance hoặc gọi method.

Bài này tập trung vào **reflection trên `Class<?>` đã có**, không yêu cầu tự xây dựng bytecode generator. Một ví dụ nhỏ sẽ tạo hidden class từ bytecode của lớp mẫu đã biên dịch để có dữ liệu chạy độc lập; sau khi nhận `Class<?>`, phần chính là **đọc metadata và thao tác reflection**.

Sau bài học, bạn sẽ có thể:

- Dùng `Class.isHidden()` (Since 15) để nhận biết hidden class.
- Hiểu `getName()` của hidden class khác binary name, còn `getCanonicalName()` trả `null`.
- Dùng `getDeclaredMethods()`, `getDeclaredMethod(...)`, `getDeclaredFields()`, `getDeclaredField(...)` và `getDeclaredConstructor(...)` trên `Class<?>` đã nhận.
- Hiểu khác biệt giữa **tìm metadata** và **có quyền truy cập / gọi member**.
- Gọi constructor, gọi method bằng `java.lang.reflect` và kiểm tra `isInstance(...)` khi điều kiện truy cập cho phép.
- Tránh dựa vào tên runtime không ổn định, không coi hidden class là một lớp có thể tải lại bằng tên.

## 2. Hidden class khác lớp thông thường như thế nào?

Ví dụ với lớp thông thường:

```java
Class<?> normal = String.class;
System.out.println(normal.isHidden()); // false
System.out.println(normal.getName());  // java.lang.String
```

Một lớp thông thường có **binary name** (ví dụ `java.lang.String`), nên thường có thể tra cứu qua `Class.forName("java.lang.String")` nếu lớp nằm trong phạm vi tải phù hợp.

Một hidden class được tạo bởi `MethodHandles.Lookup.defineHiddenClass(...)` lại có các đặc điểm:

| Chủ đề | Lớp thông thường | Hidden class |
| --- | --- | --- |
| Có `Class<?>` đại diện | Có | **Có** |
| `Class.isHidden()` | `false` | **`true`** |
| `Class.getName()` | Binary name, ví dụ `pkg.Sample` | Tên có dạng `N/suffix`, có dấu `/` |
| `Class.getCanonicalName()` | Có thể có canonical name | **`null`** |
| Có thể tìm bằng `Class.forName(...)` | Thông thường có, tùy class loader | **Không** |
| Xem field/method/constructor bằng reflection khi đã có `Class<?>` | Có | **Có** |
| Gọi method bằng reflection nếu đủ quyền | Có | **Có** |
| Có thể viết class literal `HiddenType.class` trong mã độc lập | Có đối với kiểu có tên truy cập được | Không thể gọi tên hidden class bằng cú pháp Java bình thường |

Tên của hidden class mang một hậu tố do JVM gán, ví dụ ở dạng khái niệm `sample.Generated/0x...`. **Không hard-code hậu tố**: nó không phải tên ổn định để cấu hình, serialize hay gọi `Class.forName`. Hãy giữ và truyền **tham chiếu `Class<?>` thực tế**, hoặc truyền instance/handle được API sinh lớp cung cấp.

Đừng suy luận `isHidden()` từ tên `$`, `isSynthetic()`, `isAnonymousClass()` hay vị trí trong package. Đó là các khái niệm khác nhau. Phương thức trả lời đúng câu hỏi về hidden class là **`Class.isHidden()`**.

## 3. Lấy đối tượng Class đã tồn tại từ đâu?

Các đường nhận `Class<?>` vẫn đúng với Java hiện hành:

1. **Framework / code sinh lớp:** thành phần định nghĩa hidden class trả về `MethodHandles.Lookup`; `lookup.lookupClass()` là đối tượng `Class<?>` đại diện cho hidden class đó.
2. **Đã có instance:** `instance.getClass()` trả `Class<?>` thực của đối tượng, kể cả khi kiểu runtime là hidden class.
3. **API trả `Class<?>` hoặc `java.lang.reflect.Member`:** dùng trực tiếp class reference được cung cấp; không cần suy ngược tên rồi tải lại.
4. **Thông tin reflection khác:** `Method.getDeclaringClass()`, `Field.getDeclaringClass()`, `Constructor.getDeclaringClass()` cho biết class thực sự khai báo thành viên.

Mấu chốt là **đối tượng `Class<?>` đã có**. Nếu một API trả `Class<?> hiddenType`, bạn có thể sử dụng:

```java
boolean hidden = hiddenType.isHidden();
String runtimeName = hiddenType.getName();
java.lang.reflect.Method[] declared = hiddenType.getDeclaredMethods();
```

Đây là **mã trong ngữ cảnh đã có biến `hiddenType`**, không phải chương trình chạy độc lập. Không cần và không thể “khôi phục” hidden class bằng `Class.forName(runtimeName)`.

**Phân biệt hai việc:** định nghĩa hidden class từ bytecode bằng `Lookup.defineHiddenClass` là việc của thành phần sở hữu bytecode và quyền lookup. Reflection trên `Class<?>` đã được trả về chỉ cần Class reference, nhưng vẫn phải tuân theo kiểm tra quyền truy cập khi thao tác với member.

## 4. Những phương thức reflection quan trọng trên Class

### 4.1. Nhận dạng và đọc metadata

| API | Kết quả / ý nghĩa |
| --- | --- |
| `type.isHidden()` | `true` nếu đối tượng đại diện hidden class |
| `type.getName()` | Tên runtime, với hidden class dạng `N/suffix`, không phải binary name |
| `type.getCanonicalName()` | `null` với hidden class |
| `type.getPackageName()` | Tên package, khi cần kiểm tra ngữ cảnh |
| `type.getModule()` | Module chứa class, hữu ích khi hiểu giới hạn truy cập |
| `type.getClassLoader()` | Defining loader được liên kết với class; không biến tên hidden class thành tên có thể tải lại |
| `type.isInstance(value)` | Kiểm tra một object có tương thích với type này hay không |
| `type.isAssignableFrom(otherType)` | Kiểm tra quan hệ gán kiểu giữa hai đối tượng `Class<?>` |

`getName()` trên hidden class theo Javadoc là `N + "/" + suffix`, với `N` lấy từ tên trong class file dùng để định nghĩa. Ký tự `/` làm chuỗi kết quả **không phải binary name hợp lệ**. `getCanonicalName() == null` cũng đúng với **một số loại class khác** như local/anonymous class, vì vậy riêng kết quả `null` không chứng minh đó là hidden class; cần `isHidden()`.

### 4.2. Method, field và constructor

| API | Phạm vi tra cứu |
| --- | --- |
| `getDeclaredMethods()` | Các method **khai báo trực tiếp**, gồm public và non-public; không bao gồm method chỉ được kế thừa |
| `getMethods()` | Các public method của type và các public method kế thừa |
| `getDeclaredMethod("m", types...)` | Tìm method khai báo trực tiếp có tên và **kiểu tham số chính xác** |
| `getDeclaredFields()` | Các field khai báo trực tiếp, kể cả private |
| `getDeclaredField("f")` | Tìm field khai báo trực tiếp theo tên |
| `getDeclaredConstructors()` | Các constructor được khai báo |
| `getDeclaredConstructor(types...)` | Tìm constructor theo kiểu tham số |
| `getInterfaces()`, `getSuperclass()` | Đọc quan hệ kiểu khi thích hợp |

**Không nhầm việc lấy đối tượng `Method`/`Field` với quyền gọi hoặc đọc member.** Ví dụ, `getDeclaredField("secret")` có thể trả metadata của field `private`, nhưng `field.get(instance)` vẫn phải vượt qua các kiểm tra truy cập tương ứng. Với JDK có module system, cả strong encapsulation/module openness đều có thể ảnh hưởng đến `trySetAccessible()`.

Thứ tự phần tử trong các mảng từ `getDeclaredMethods()` hoặc `getDeclaredFields()` **không phải hợp đồng sắp xếp ổn định**. Nếu framework cần thứ tự để hiển thị, tự sort theo tiêu chí riêng; đừng dùng chỉ số `methods[0]` rồi mặc định đó là method mong đợi.

## 5. Ví dụ Java 15+ độc lập: đã có Class<?> rồi phản chiếu

Chương trình sau dùng lớp `Template` làm nguồn bytecode đáng tin cậy. Phần tạo hidden class chỉ giúp bạn có một `Class<?>` để quan sát, không phải yêu cầu tự xây một bộ sinh bytecode. Mọi thao tác đọc và gọi sau đó đều dựa vào **`hiddenType`**.

Lưu chương trình thành **`HiddenReflectionDemo.java`**:

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public final class HiddenReflectionDemo {
    public static final class Template {
        public Template() {}

        public String greet(String who) {
            return "Hello, " + who;
        }

        private final int code = 7;
    }

    public static void main(String[] args) throws Exception {
        // Chỉ để tạo bytecode mẫu có thật, đã biên dịch cùng chương trình.
        byte[] bytes;
        try (InputStream stream = Template.class.getResourceAsStream(
                "HiddenReflectionDemo$Template.class")) {
            if (stream == null) {
                throw new IllegalStateException("class bytes unavailable");
            }
            bytes = stream.readAllBytes();
        }

        // Java 15+: định nghĩa một hidden class từ bytecode đáng tin cậy.
        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(bytes, false);

        // Từ đây, giả sử hệ thống đã có Class<?> này.
        Class<?> hiddenType = hiddenLookup.lookupClass();

        System.out.println("isHidden: " + hiddenType.isHidden());
        System.out.println("ordinaryIsHidden: " + Template.class.isHidden());
        System.out.println("nameHasSlash: "
                + hiddenType.getName().contains("/"));
        System.out.println("canonicalNull: "
                + (hiddenType.getCanonicalName() == null));
        System.out.println("sameType: "
                + (hiddenType == Template.class));

        // Reflection trên chính Class<?> đã được cung cấp.
        Constructor<?> constructor = hiddenType.getDeclaredConstructor();
        Method greet = hiddenType.getDeclaredMethod("greet", String.class);
        Field field = hiddenType.getDeclaredField("code");
        Object object = constructor.newInstance();

        System.out.println("constructorNameMatches: "
                + (constructor.getDeclaringClass() == hiddenType));
        System.out.println("methodName: " + greet.getName());
        System.out.println("fieldType: " + field.getType().getName());
        System.out.println("instanceOfHidden: "
                + hiddenType.isInstance(object));
        System.out.println("invoke: " + greet.invoke(object, "Lan"));

        // Hidden class không thể tìm lại theo getName().
        try {
            Class.forName(hiddenType.getName());
            System.out.println("forName: unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("forName: ClassNotFoundException");
        }
    }
}
```

Chạy với một JDK hỗ trợ target Java 15:

```bash
javac --release 15 HiddenReflectionDemo.java
java HiddenReflectionDemo
```

**Stdout chính xác** (ví dụ đã được biên dịch bằng `javac --release 15` và chạy trên JDK hiện đại):

```text
isHidden: true
ordinaryIsHidden: false
nameHasSlash: true
canonicalNull: true
sameType: false
constructorNameMatches: true
methodName: greet
fieldType: int
instanceOfHidden: true
invoke: Hello, Lan
forName: ClassNotFoundException
```

Chương trình tránh in toàn bộ `getName()` vì suffix hidden class do JVM gán có thể thay đổi qua mỗi lần chạy. Thay vì so sánh tên động với một chuỗi cụ thể, kiểm tra thuộc tính ổn định là **có dấu `/`** và `isHidden() == true`.

### 5.1. Giải thích kết quả và flow

1. `Template.class.getResourceAsStream(...)` đọc file `HiddenReflectionDemo$Template.class` mà `javac` đã tạo. Nếu thiếu file này, chương trình báo lỗi rõ ràng. `InputStream.readAllBytes()` là API có từ trước Java 15 và vẫn dùng được.
2. `MethodHandles.lookup().defineHiddenClass(bytes, false)` tạo một **lớp mới** từ bytes và trả `Lookup` liên kết với lớp đó. `false` có nghĩa không yêu cầu khởi tạo ngay tại lời gọi định nghĩa; dùng constructor về sau sẽ dẫn đến khởi tạo phù hợp. Đây là dữ liệu bytecode của chương trình mẫu, không phải bytecode do người dùng tùy ý cung cấp.
3. `hiddenLookup.lookupClass()` trả `Class<?> hiddenType`. Từ đây đối tượng Class là **nguồn thông tin thực**, không cần biết tên sinh động của lớp.
4. `Template.class.isHidden() == false` nhưng `hiddenType.isHidden() == true`: cùng mẫu bytecode không có nghĩa hai kiểu là cùng một class runtime.
5. `getDeclaredConstructor()` tìm constructor không tham số. `getDeclaredMethod("greet", String.class)` tìm method có tham số `String`. `getDeclaredField("code")` tìm field private và chỉ đọc **kiểu của field** (`int`).
6. Vì constructor và method trong mẫu được khai báo `public` và quyền truy cập phù hợp, `constructor.newInstance()` tạo instance và `greet.invoke(object, "Lan")` trả `"Hello, Lan"`.
7. `hiddenType.isInstance(object)` trả true, chứng minh object vừa tạo thuộc kiểu runtime hidden class.
8. `Class.forName(hiddenType.getName())` ném `ClassNotFoundException` vì chuỗi từ `getName()` không phải binary name có thể dùng để tìm hidden class.

**Lưu ý khi chạy:** ví dụ được viết để biên dịch từ file nguồn và giữ cả file `.class` của lớp lồng nhau trong classpath; đừng chỉ sao chép file `HiddenReflectionDemo.class` mà bỏ `HiddenReflectionDemo$Template.class`. Thực thi trong dự án module hoặc framework cần tuân theo quy tắc đóng gói resource/class file tương ứng.

## 6. Đã có instance thì dùng getClass(), không tìm theo tên

Trong ứng dụng thực tế, framework có thể trả cho bạn một object mà kiểu runtime là hidden class; bạn không nhất thiết thấy bước `defineHiddenClass`:

```java
Object generatedInstance = getObjectFromFramework(); // Hàm minh họa.
Class<?> actualType = generatedInstance.getClass();

if (actualType.isHidden()) {
    Method method = actualType.getDeclaredMethod("greet", String.class);
    // Chỉ invoke khi chữ ký và quyền truy cập phù hợp.
}
```

Đoạn này **chỉ minh họa bên trong phương thức**, vì `getObjectFromFramework()` là tên mô tả, không phải API Java thật. Trong mã sản xuất, thay bằng phương thức thực tế của framework bạn dùng; không tự suy đoán API nào sẽ trả hidden class.

Khi đã có `generatedInstance` và `actualType`, phương thức `isInstance` là cách kiểm tra khả năng gán kiểu. Nhưng `generatedInstance instanceof SomeKnownInterface` vẫn có thể phù hợp **nếu** hidden class triển khai interface có tên mà chương trình biết trước. Việc hidden class không thể bị gọi tên trực tiếp **không ngăn** object của nó được sử dụng qua interface/superclass hoặc reflection nếu hệ thống thiết kế như vậy.

Nếu framework chỉ trả một **chuỗi tên lớp**, mà không cung cấp `Class<?>`, instance hoặc một registry/API do framework quản lý, bạn không thể giả định việc gọi `Class.forName(name)` sẽ khôi phục lại hidden class đó. Thiết kế API nên chuyển một handle hoặc interface/đối tượng cụ thể khi cần tương tác tiếp.

## 7. Tìm metadata không đồng nghĩa có quyền truy cập

Java Reflection vẫn thực hiện access checks. Thông thường:

- `getDeclaredMethod`/`getDeclaredField` có thể cho bạn metadata của member non-public, nhưng `invoke`/`get`/`set` có thể ném `IllegalAccessException` khi thiếu quyền.
- `Method.invoke` có thể ném `InvocationTargetException`, bọc ngoại lệ do chính method được gọi phát sinh. Khi xử lý lỗi, xem `getCause()` để nhận lỗi nghiệp vụ gốc.
- `getDeclaredMethod` không thấy tên/chữ ký cần tìm thì ném `NoSuchMethodException`; `getDeclaredField` tương tự có `NoSuchFieldException`.
- `Constructor.newInstance` có thể ném lỗi về kiểu abstract/constructor, argument hoặc ngoại lệ từ constructor; ví dụ trên có constructor công khai không tham số.
- `trySetAccessible()` chỉ giúp mở quyền truy cập **nếu Java access/module policy cho phép**. Nó có thể trả `false`; không nên dựa vào can thiệp module bằng `--add-opens` trừ khi thực sự có hợp đồng vận hành hợp lệ.

Ví dụ **chỉ để minh họa** khi bạn đã có `Field field` và `Object object`:

```java
if (field.trySetAccessible()) {
    Object value = field.get(object);
    System.out.println(value);
} else {
    System.out.println("Cannot access field in this module context");
}
```

Ở ví dụ hoàn chỉnh mục 5, ta **không cần** truy cập nội dung private field `code`: `field.getType()` chỉ đọc metadata, không yêu cầu đọc giá trị. Việc phân biệt này giúp chương trình hoạt động ổn định hơn khi dùng module boundaries.

**Hidden class không phải cơ chế sandbox hay một ranh giới bảo mật tuyệt đối.** Nó chủ yếu giới hạn khả năng tham chiếu và khám phá lớp bằng binary name. Quyền thực thi/reflection và phân quyền dữ liệu vẫn là vấn đề độc lập của hệ thống.

## 8. Những chi tiết kỹ thuật quan trọng khi xử lý hidden class

### 8.1. Tên runtime không ổn định

Javadoc `Class.getName()` đối với hidden class mô tả tên dạng `N + "/" + suffix`, trong đó hậu tố do JVM tạo. Vì vậy:

- Không lưu `getName()` vào cơ sở dữ liệu rồi mong `Class.forName(...)` load lại sau khi restart.
- Không đặt luật nghiệp vụ dựa vào nội dung suffix; một bản triển khai JVM có thể tạo suffix khác.
- Không dùng tên class như khóa nhận dạng duy nhất xuyên process: một tên tương tự không đủ chứng minh cùng **type identity**.
- Nếu cần cache metadata lúc runtime, dùng `Class<?>`/handle do hệ thống thực sự nắm giữ; cân nhắc vòng đời cache vì giữ Class reference có thể ảnh hưởng đến khả năng giải phóng lớp.

### 8.2. Class identity và class loader

Hai đối tượng `Class<?>` từ **hai lần định nghĩa hidden class riêng biệt** vẫn có thể biểu thị hai kiểu runtime khác nhau dù bytecode đầu vào giống nhau. Ví dụ mục 5 xác nhận `hiddenType != Template.class`. Không nên coi chuỗi `getName()` là nguồn xác thực type identity; dùng object `Class<?>`, kiểm tra `isInstance`/`isAssignableFrom` khi cần.

Hidden classes được thiết kế để có thể được GC giải phóng độc lập với class loader trong cấu hình mặc định, khi không còn tham chiếu giữ chúng sống. `ClassOption.STRONG` là lựa chọn khác về quan hệ vòng đời với class loader. Đây là chi tiết thiết kế hạ tầng; khi chỉ phản chiếu một `Class<?>` đã có, bạn **không cần** tự thay đổi cấu hình unload. Đừng tạo cache toàn cục giữ vô hạn mọi hidden `Class<?>` mà không xác định vòng đời.

### 8.3. Nestmate và truy cập private

`Lookup.defineHiddenClass` có tùy chọn `MethodHandles.Lookup.ClassOption.NESTMATE`: hidden class có thể được gắn vào nest của lookup class, hữu ích khi framework cần truy cập private members giữa các nestmates. Nếu **không** cung cấp tùy chọn này, không được mặc định hidden class là nestmate của caller chỉ vì dùng bytecode của một lớp lồng nhau.

Tùy chọn `NESTMATE` ảnh hưởng đến quy tắc quyền truy cập và thiết kế sinh class, nhưng **không làm `Class.forName` tải được hidden class**. Đối với một Class object đã có, hãy kiểm tra khả năng truy cập thực tế, không suy đoán quyền từ nguồn bytecode hay từ tên class.

### 8.4. Reflection và MethodHandles

`java.lang.reflect.Method`/`Constructor` phù hợp khi cần kiểm tra metadata hoặc gọi member dựa trên thông tin runtime. Với hạ tầng cần gọi lặp nhiều lần hoặc có sẵn privileged `Lookup`, có thể cân nhắc `java.lang.invoke.MethodHandle` được tạo từ lookup phù hợp. Hai cách có cơ chế kiểm tra access khác nhau: tạo method handle là bước kiểm tra quyền theo lookup, còn `Method.invoke` thực hiện access check ở lời gọi theo hợp đồng reflection.

Đừng ép chuyển sang method handles chỉ vì class hidden; reflection vẫn được hỗ trợ và có giá trị khi bạn đã có `Class<?>`.

## 9. Kiểm thử thực tế và các lỗi dễ nhầm

Nên kiểm thử các nhóm sau, không phụ thuộc suffix runtime:

| Ca kiểm tra | Kỳ vọng |
| --- | --- |
| `normalType.isHidden()` | `false` |
| `hiddenType.isHidden()` | `true` |
| `hiddenType.getCanonicalName() == null` | `true` |
| `hiddenType.getName().contains("/")` | `true` |
| `hiddenType == Template.class` | `false` |
| `getDeclaredMethod("greet", String.class)` | Tìm đúng method |
| `getDeclaredField("code").getType()` | `int.class` |
| `constructor.newInstance()` | Tạo instance nếu có quyền |
| `hiddenType.isInstance(instance)` | `true` |
| `greet.invoke(instance, "Lan")` | `"Hello, Lan"` |
| `Class.forName(hiddenType.getName())` | `ClassNotFoundException` |

Các lỗi thường gặp:

1. **Tưởng hidden class không có `Class<?>`:** Sai. Đã có Class object thì introspection thông thường vẫn hoạt động.
2. **Dùng `Class.forName(hiddenType.getName())`:** Sai. `getName()` không phải binary name của một lớp có thể discover; hãy giữ Class/instance/lookup gốc.
3. **Dựa vào suffix cố định trong test:** Sai. Hậu tố runtime có thể thay đổi, nên kiểm tra các tính chất ổn định thay vì so sánh toàn bộ chuỗi tên.
4. **Dùng `getMethods()` khi cần private member khai báo trực tiếp:** Nên dùng `getDeclaredMethods()`/`getDeclaredMethod(...)` để tìm metadata, rồi kiểm tra quyền riêng.
5. **Nghĩ `getDeclaredField` tự cho quyền đọc private field:** Sai. Metadata và quyền truy cập giá trị là hai vấn đề khác nhau.
6. **Giả định `getDeclaredMethods()` được sắp theo source:** Không có thứ tự bảo đảm; tự sort nếu cần hiển thị ổn định.
7. **Coi cùng bytecode nghĩa là cùng Class:** Sai. Hai lần định nghĩa lớp có thể tạo hai kiểu khác nhau.
8. **Coi hidden là từ khóa bảo mật:** Sai. Hidden class chỉ hạn chế một số cách tham chiếu/khám phá; không thay thế access control và thiết kế quyền.
9. **Dùng bytecode không đáng tin cậy làm đầu vào `defineHiddenClass`:** Sinh lớp động là thao tác mạnh; chỉ dùng bytecode có nguồn kiểm soát, được kiểm tra và được cấu hình quyền phù hợp.
10. **Tưởng `getCanonicalName()==null` chỉ xảy ra ở hidden class:** Sai. Local/anonymous classes cũng có thể không có canonical name; dùng `isHidden()`.

## 10. Luyện tập có đáp án

**Câu 1.** Bạn nhận được `Class<?> c` do một framework trả về và `c.isHidden()==true`. Có nên gọi `Class.forName(c.getName())` để xác nhận tồn tại không?

**Đáp án:** Không. `c` đã là Class object tồn tại; hidden class không có binary name có thể tìm lại bằng `Class.forName`. Kiểm tra trực tiếp trên `c` bằng các API reflection cần thiết.

**Câu 2.** `c.getDeclaredField("token")` trả về `Field` thì `field.get(instance)` có chắc chạy không?

**Đáp án:** Không. Tìm metadata khác quyền đọc field. Nếu member không được truy cập từ caller, `get` có thể ném `IllegalAccessException`; `trySetAccessible` cũng phải tuân theo module policy.

**Câu 3.** Tại sao `c.getName()` có dấu `/` nhưng `c.getCanonicalName()==null`?

**Đáp án:** Hidden class có tên runtime phục vụ định danh và debug theo dạng `N/suffix`, nhưng không có canonical/binary name như class có tên thông thường.

**Câu 4.** Hai hidden class được define từ cùng bytecode có nhất thiết là cùng type không?

**Đáp án:** Không. Các lần định nghĩa có thể cho Class object/type identity riêng. Dùng object `Class<?>` nhận được hoặc `isInstance` để kiểm tra quan hệ thực tế.

**Câu 5.** Khi muốn gọi `greet(String)`, vì sao phải dùng `getDeclaredMethod("greet", String.class)`?

**Đáp án:** Reflection cần đúng tên và **kiểu tham số** để chọn overload phù hợp. Nếu chỉ gọi tên, bạn có thể không phân biệt các phương thức cùng tên nhưng khác chữ ký.

**Câu 6.** Nếu mục tiêu chỉ là xem private field có kiểu gì, có cần `setAccessible(true)` không?

**Đáp án:** Không nhất thiết. `getDeclaredField(...).getType()` đọc metadata; việc đọc/ghi giá trị private field mới cần xét quyền truy cập.

**Tiêu chí hoàn thành:** bạn có thể nhận một `Class<?>` hiện hữu, xác định nó có hidden hay không, tìm một method/field/constructor theo chữ ký, gọi được các member mà caller có quyền, và giải thích vì sao không thể tìm lại hidden class chỉ qua `getName()`.

## 11. Tài liệu chính thức còn áp dụng

- [JEP 371 – Hidden Classes](https://openjdk.org/jeps/371): mục tiêu, đặc tính không discoverable bằng binary name, vòng đời và những tương tác với reflection.
- [Java SE 15 – `Class`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/Class.html): `isHidden` (Since 15), `getName`, `getCanonicalName`, `getDeclaredMethod`, `getDeclaredField`.
- [Java SE 25 – `Class`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): đối chiếu hợp đồng API vẫn được tài liệu hóa trong JDK hiện đại.
- [Java SE 15 – `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, `lookupClass` và quyền lookup.
- [Java SE 15 – `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` và `STRONG`.
- [Java SE 25 – `java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html): `invoke` và các ngoại lệ khi phản chiếu thành viên.
- [Java SE 25 – `java.lang.reflect.AccessibleObject`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible` và các điều kiện module access.

**Ghi nhớ:** Hidden class khó tìm **bằng tên**, nhưng khi đã nắm `Class<?>` thì bạn vẫn có thể phản chiếu metadata và thao tác trên member theo các quy tắc truy cập của Java.