# Tên và định danh kiểu trong Java Reflection: `getName()`, `getSimpleName()`, `getCanonicalName()` và `getTypeName()`

Khi dùng Reflection, một đối tượng `Class<?>` cho biết kiểu ở thời điểm chạy. Java cung cấp nhiều cách lấy tên của kiểu vì **tên JVM dùng để định danh**, **tên ngắn dùng để hiển thị**, **tên chuẩn trong mã nguồn** và **biểu diễn tên của `Type`** phục vụ các mục đích khác nhau. Chúng thường trùng nhau với lớp thông thường nhưng khác rõ ở lớp lồng nhau, mảng, lớp cục bộ, lớp vô danh và kiểu generic.

## 1. Phạm vi và mô hình tên

Bài học tập trung vào bốn phương thức:

- `Class#getName()`: lấy *binary name* của lớp/interface thông thường; với mảng trả về dạng tên JVM được mã hóa, với kiểu nguyên thủy trả về từ khóa kiểu.
- `Class#getSimpleName()`: lấy tên ngắn, không có tên gói hay tên lớp bao ngoài; có thể là chuỗi rỗng với lớp vô danh.
- `Class#getCanonicalName()`: lấy tên *canonical* theo cách biểu diễn trong mã nguồn Java; có thể trả về `null`.
- `Class#getTypeName()`: lấy tên biểu diễn kiểu dễ đọc hơn cho mảng; với lớp thông thường nhìn chung giống `getName()`. Cùng tên phương thức này cũng có trên giao diện `java.lang.reflect.Type` để biểu diễn các kiểu generic.

**Phân biệt ngay từ đầu:** `Class` biểu diễn kiểu runtime đã chịu ảnh hưởng của *type erasure*. Trong khi đó, `Type` có thể là `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType` hoặc `GenericArrayType`; kết quả `Type#getTypeName()` phụ thuộc vào dạng `Type` thực tế. Bởi vậy gọi `getTypeName()` trên `Class<?>` không tự làm xuất hiện tham số kiểu như `<String>`.

## 2. Bảng so sánh bốn phương thức

| Phương thức | Ý nghĩa chính | Kiểu mảng | Lớp thành viên (member class) | Khả năng `null`/rỗng |
| --- | --- | --- | --- | --- |
| `getName()` | Tên dùng ở mức runtime/JVM | Mã hóa như `[I`, `[Ljava.lang.String;` | Dùng dấu `$` giữa lớp bao ngoài và lớp thành viên | Không trả về `null` |
| `getSimpleName()` | Tên ngắn để trình bày | `int[]`, `String[][]` | Chỉ còn `Entry`, `Nested`... | `""` đối với lớp vô danh |
| `getCanonicalName()` | Tên chuẩn kiểu viết trong mã nguồn | `int[]`, `java.lang.String[][]` | Dùng dấu chấm: `java.util.Map.Entry` | `null` nếu không có canonical name, điển hình ở lớp local/anonymous |
| `getTypeName()` trên `Class` | Tên biểu diễn kiểu | `int[]`, `java.lang.String[][]` | Dùng tên binary có `$` | Không tự cung cấp tham số generic |

Ví dụ cùng một kiểu `java.util.Map.Entry`:

- `Map.Entry.class.getName()` → `"java.util.Map$Entry"`.
- `Map.Entry.class.getSimpleName()` → `"Entry"`.
- `Map.Entry.class.getCanonicalName()` → `"java.util.Map.Entry"`.
- `Map.Entry.class.getTypeName()` → `"java.util.Map$Entry"`.

Ký tự `$` nằm trong binary name của kiểu thành viên. Không nên tự động đổi tất cả `$` thành dấu chấm, vì `$` cũng có thể xuất hiện trong tên lớp được khai báo hợp lệ và trong tên các lớp do trình biên dịch sinh.

## 3. Quy tắc theo từng loại kiểu

### 3.1. Lớp thông thường, interface, primitive và `void`

Với `String.class`, ba cách lấy tên có chứa package đều cho `java.lang.String`, còn `getSimpleName()` là `String`. Với primitive `int.class`, cả bốn phương thức đều cho `int`; tương tự `boolean.class` cho `boolean`. `void.class` là đối tượng `Class` hợp lệ để biểu diễn kiểu `void`; không có kiểu mảng `void[]` trong Java.

`getSimpleName()` không đủ làm định danh duy nhất: `java.util.Date` và `java.sql.Date` đều có tên ngắn `Date`.

### 3.2. Lớp thành viên và lớp lồng nhau

Với `java.util.Map.Entry` (interface thành viên của `Map`), tên binary là `java.util.Map$Entry`, canonical name là `java.util.Map.Entry`, còn simple name là `Entry`. Quy tắc này cũng áp dụng cho lớp `static nested` và lớp thành viên không `static`. Việc đổi dấu chấm thành `$` chỉ có ý nghĩa ở phần tên kiểu lồng nhau; dấu chấm ngăn các package vẫn giữ nguyên.

### 3.3. Mảng và mã hóa tên mảng trong JVM

`Class#getName()` của lớp mảng theo quy tắc:

1. Mỗi chiều mảng có một ký tự `[`.
2. Thành phần primitive sử dụng mã kiểu JVM: `Z` = `boolean`, `B` = `byte`, `C` = `char`, `S` = `short`, `I` = `int`, `J` = `long`, `F` = `float`, `D` = `double`.
3. Thành phần kiểu tham chiếu dùng `L` + binary name + `;`. Trong tên do `Class#getName()` trả về, các dấu chấm package nằm trong binary name, ví dụ `[Ljava.lang.String;`.

| Biểu thức | `getName()` | `getSimpleName()` | `getCanonicalName()` | `getTypeName()` |
| --- | --- | --- | --- | --- |
| `int[].class` | `[I` | `int[]` | `int[]` | `int[]` |
| `String[][].class` | `[[Ljava.lang.String;` | `String[][]` | `java.lang.String[][]` | `java.lang.String[][]` |
| `Map.Entry[].class` | `[Ljava.util.Map$Entry;` | `Entry[]` | `java.util.Map.Entry[]` | `java.util.Map$Entry[]` |

Đừng nhầm chuỗi do `Class#getName()` trả về với cú pháp descriptor trong tệp class, nơi tên nội bộ kiểu tham chiếu thường dùng dấu gạch chéo `/` thay cho dấu chấm `.`. Nếu đang viết tài liệu hoặc giao diện cho người đọc, `getTypeName()` hoặc `getCanonicalName()` thường dễ hiểu hơn `getName()` ở trường hợp mảng.

### 3.4. Lớp cục bộ (local class), lớp vô danh (anonymous class)

Một local class khai báo trong thân phương thức có simple name, nhưng thường **không có canonical name**: `getCanonicalName() == null`. Lớp vô danh có `getSimpleName().isEmpty() == true` và cũng không có canonical name. Binary name của chúng do trình biên dịch sinh, thường chứa các thành phần như `$1Local` hoặc `$1`; số và cấu trúc chính xác không nên được dùng làm hợp đồng nghiệp vụ.

Mảng có thành phần là kiểu không có canonical name cũng không có canonical name. Ví dụ một mảng của local class không đột nhiên trở thành kiểu có canonical name.

## 4. Ví dụ Java 17+: so sánh trực tiếp

Tạo tệp **`ClassNameDemo.java`**:

~~~java
import java.util.Map;

public class ClassNameDemo {
    private static void show(String label, Class<?> type) {
        System.out.println(label);
        System.out.println("  getName          = " + type.getName());
        System.out.println("  getSimpleName    = " + type.getSimpleName());
        System.out.println("  getCanonicalName = " + type.getCanonicalName());
        System.out.println("  getTypeName      = " + type.getTypeName());
    }

    public static void main(String[] args) {
        show("String", String.class);
        show("int", int.class);
        show("int[]", int[].class);
        show("String[][]", String[][].class);
        show("Map.Entry", Map.Entry.class);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ClassNameDemo.java
java ClassNameDemo
~~~

**Kết quả stdout:**

~~~text
String
  getName          = java.lang.String
  getSimpleName    = String
  getCanonicalName = java.lang.String
  getTypeName      = java.lang.String
int
  getName          = int
  getSimpleName    = int
  getCanonicalName = int
  getTypeName      = int
int[]
  getName          = [I
  getSimpleName    = int[]
  getCanonicalName = int[]
  getTypeName      = int[]
String[][]
  getName          = [[Ljava.lang.String;
  getSimpleName    = String[][]
  getCanonicalName = java.lang.String[][]
  getTypeName      = java.lang.String[][]
Map.Entry
  getName          = java.util.Map$Entry
  getSimpleName    = Entry
  getCanonicalName = java.util.Map.Entry
  getTypeName      = java.util.Map$Entry
~~~

**Giải thích:** `String` là lớp cấp cao nhất nên `getName()`, `getCanonicalName()` và `getTypeName()` trùng nhau. `int` cũng không tạo khác biệt. Với `int[]`, chỉ `getName()` trả về mã `[I`. Với `String[][]`, tên JVM bắt đầu bằng hai dấu `[`. Với `Map.Entry`, sự khác nhau nằm ở ký tự `$` và dấu chấm giữa hai tên kiểu.

## 5. Ví dụ local class và anonymous class không phụ thuộc số do compiler sinh

Tạo tệp **`LocalAnonymousDemo.java`**:

~~~java
public class LocalAnonymousDemo {
    private static void show(String label, Class<?> type) {
        System.out.println(label
                + ": local=" + type.isLocalClass()
                + ", anonymous=" + type.isAnonymousClass()
                + ", canonicalPresent=" + (type.getCanonicalName() != null)
                + ", simpleNameEmpty=" + type.getSimpleName().isEmpty());
    }

    public static void main(String[] args) {
        class Local {}

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                // Ví dụ chỉ kiểm tra metadata của lớp vô danh.
            }
        };

        show("Local", Local.class);
        show("Anonymous", anonymous.getClass());
    }
}
~~~

~~~bash
javac LocalAnonymousDemo.java
java LocalAnonymousDemo
~~~

**Kết quả stdout:**

~~~text
Local: local=true, anonymous=false, canonicalPresent=false, simpleNameEmpty=false
Anonymous: local=false, anonymous=true, canonicalPresent=false, simpleNameEmpty=true
~~~

Nếu in thêm `getName()` hoặc `getTypeName()` của hai lớp này, kết quả chứa tên do compiler đặt; tên ấy có thể thay đổi khi chỉnh cấu trúc mã hoặc đổi compiler. `getSimpleName()` của local class là `Local`, còn của anonymous class là chuỗi rỗng. Đây là lý do phải kiểm tra `null` trước khi dùng `getCanonicalName()` và không lấy tên compiler sinh làm khóa dữ liệu ổn định.

## 6. `Type#getTypeName()` và generic: điểm dễ nhầm nhất

`Class<?>` cho biết kiểu runtime. Do Java xóa phần lớn thông tin tham số kiểu của đối tượng ở runtime (*type erasure*), `List.class.getTypeName()` chỉ cho `java.util.List`. Tuy nhiên chữ ký generic của field, method hoặc parameter có thể được lưu trong metadata của lớp biên dịch. Reflection có API riêng để đọc chúng:

- `Field#getType()` trả về một `Class<?>`: kiểu thô ở runtime.
- `Field#getGenericType()` trả về một `Type`, có thể là `ParameterizedType`: giữ cấu trúc như `List<String>` nếu metadata khai báo chứa nó.
- `Method#getReturnType()` so với `Method#getGenericReturnType()` và `Parameter#getType()` so với `Parameter#getParameterizedType()` tuân theo cùng cách phân biệt kiểu thô với kiểu generic.

Tạo tệp **`GenericTypeNamesDemo.java`**:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.List;

public class GenericTypeNamesDemo {
    private List<String> names;

    public static void main(String[] args) throws NoSuchFieldException {
        Field field = GenericTypeNamesDemo.class.getDeclaredField("names");

        Class<?> rawType = field.getType();
        Type genericType = field.getGenericType();

        System.out.println("Class#getTypeName = " + rawType.getTypeName());
        System.out.println("Type#getTypeName  = " + genericType.getTypeName());
        System.out.println("ParameterizedType = "
                + (genericType instanceof ParameterizedType));
    }
}
~~~

~~~bash
javac GenericTypeNamesDemo.java
java GenericTypeNamesDemo
~~~

**Kết quả stdout:**

~~~text
Class#getTypeName = java.util.List
Type#getTypeName  = java.util.List<java.lang.String>
ParameterizedType = true
~~~

`Field#getGenericType()` trả về `ParameterizedType` cho khai báo `List<String>`, còn `getType()` chỉ biết `List.class`. `getTypeName()` là phương thức chung của `Type`, nên kết quả khác nhau do **đối tượng nhận lời gọi khác nhau**, chứ không phải `Class#getTypeName()` tự phục hồi tham số kiểu đã bị xóa. Với `TypeVariable`, wildcard và generic array, biểu diễn tên tiếp tục phản ánh cấu trúc của `Type` tương ứng; không nên ép mọi `Type` về `Class`.

## 7. Dùng phương thức nào trong thực tế?

| Nhu cầu | Lựa chọn | Vì sao |
| --- | --- | --- |
| Ghi log hoặc truy vết tên lớp JVM, nhất là lớp lồng | `getName()` | Thể hiện binary name; mảng có mã JVM nên có thể khó đọc |
| Tiêu đề ngắn cho UI, bảng thống kê loại đối tượng | `getSimpleName()` | Gọn, nhưng trùng tên giữa các package và có thể rỗng |
| Hiển thị tên đầy đủ gần cú pháp Java source | `getCanonicalName()` sau khi kiểm tra `null` | Phân biệt package/lớp lồng bằng dấu chấm; có thể vắng ở local/anonymous |
| Hiển thị tên runtime của mảng dễ đọc | `Class#getTypeName()` | Cho `String[]` / `int[][]` thay vì `[Ljava.lang.String;` / `[[I` |
| Trình bày generic từ field/method/parameter | `Type#getTypeName()` từ API `getGeneric...` | Có thể giữ `List<String>`, wildcard, type variable theo chữ ký đã khai báo |
| So sánh xem hai `Class<?>` có cùng định danh runtime | So sánh chính các `Class` bằng `==` | Tên chuỗi không biểu diễn đầy đủ danh tính khi có nhiều class loader |

Đoạn xử lý tên đầy đủ an toàn với `null`:

~~~java
static String displayType(Class<?> type) {
    String canonical = type.getCanonicalName();
    return canonical != null ? canonical : type.getTypeName();
}
~~~

Đây là **hàm minh họa** để đặt trong một lớp Java, không phải chương trình chạy độc lập. Nó ưu tiên canonical name khi có, rồi dùng type name để không bị lỗi `NullPointerException`; với local/anonymous class, tên fallback có thể vẫn là tên compiler sinh.

### Liên hệ `Class.forName()`: tên binary không phải lúc nào cũng là khóa tải lớp

`Class.forName(String)` thường cần **binary name** đối với lớp thông thường và lớp lồng; ví dụ `Class.forName("java.util.Map$Entry")` hoạt động, còn `Class.forName("java.util.Map.Entry")` không định vị chính kiểu lồng ấy theo cách thông thường. Với lớp mảng, tên như `[I` hoặc `[Ljava.lang.String;` được chấp nhận. Trái lại `Class.forName("int")` không tải được primitive `int.class`. Ngoài ra, tải lớp còn phụ thuộc class loader; biểu diễn tên không thay thế được danh tính `Class<?>`.

Tạo tệp **`ForNameDemo.java`**:

~~~java
import java.util.Map;

public class ForNameDemo {
    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println(Class.forName(Map.Entry.class.getName())
                == Map.Entry.class);
        System.out.println(Class.forName(int[].class.getName())
                == int[].class);
    }
}
~~~

~~~bash
javac ForNameDemo.java
java ForNameDemo
~~~

**Kết quả stdout:**

~~~text
true
true
~~~

Hai kết quả chứng minh binary name của lớp lồng và tên mã hóa của mảng đều dùng được trong hai lời gọi tương ứng. `Class.forName` có thể làm khởi tạo lớp và nên được cân nhắc kỹ khi Reflection xử lý tên do bên ngoài cung cấp.

## 8. Lỗi phổ biến và cách tự kiểm tra

1. **Dùng `getSimpleName()` làm định danh duy nhất.** Hai lớp ở hai package khác nhau vẫn có thể cùng simple name; giữ đối tượng `Class` hoặc dùng tên phù hợp với mục đích.
2. **Cho rằng `getCanonicalName()` luôn là `String` hợp lệ.** Local/anonymous class có thể trả `null`; hãy kiểm tra trước khi gọi các thao tác chuỗi.
3. **Cho rằng `getName()` của mảng là `String[]`.** Thực tế `String[].class.getName()` là `[Ljava.lang.String;`. Dùng `getTypeName()` nếu mục tiêu là trình bày dễ đọc.
4. **Cho rằng `getName()` và `getCanonicalName()` luôn giống nhau.** Với lớp thành viên: `$` khác dấu chấm; với local/anonymous có thể hoàn toàn không có canonical name.
5. **Cho rằng `Class#getTypeName()` giữ tham số generic.** Cần đọc `Field#getGenericType()`, `Method#getGenericReturnType()` hoặc API generic phù hợp trước khi gọi `Type#getTypeName()`.
6. **Tự phân tích tên bằng `split(".")` hay thay tất cả `$`.** Dấu chấm ở `String.split` là ký tự đặc biệt của regex; hơn nữa tên JVM của lớp lồng, mảng và lớp do compiler sinh có quy tắc riêng. Dùng API Reflection để lấy chính dạng tên cần thiết.
7. **Đồng nhất tên với bản sắc kiểu.** Hai lớp có cùng binary name nhưng được nạp bởi hai class loader khác nhau vẫn có thể là hai kiểu runtime khác nhau; kiểm tra `Class<?>` và class loader khi xây framework.

### Tự kiểm tra nhanh

- `byte[].class.getName()` trả `[B`, còn `byte[].class.getTypeName()` trả `byte[]`.
- `String.class.getSimpleName()` trả `String`, không kèm `java.lang`.
- `Map.Entry.class.getCanonicalName()` trả `java.util.Map.Entry`, còn `getName()` trả `java.util.Map$Entry`.
- Với local class, `getCanonicalName() == null`; với anonymous class, thêm điều kiện `getSimpleName().isEmpty()` là `true`.
- Nếu Reflection đọc field khai báo `List<String>`, `field.getType().getTypeName()` chỉ là `java.util.List`, nhưng `field.getGenericType().getTypeName()` có thể là `java.util.List<java.lang.String>`.

**Ghi nhớ:** hãy chọn phương thức theo đối tượng nhận (`Class` hay `Type`) và mục tiêu (định danh runtime, tên ngắn, tên canonical, hay trình bày generic). Chỉ cần thử với một lớp thường, một lớp lồng và một mảng là có thể thấy ba nhóm khác biệt quan trọng nhất.