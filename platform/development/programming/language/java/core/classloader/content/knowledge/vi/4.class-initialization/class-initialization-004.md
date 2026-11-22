# Các thao tác không kích hoạt khởi tạo lớp: class literal, mảng và hằng biên dịch

## 1. Bài học giải quyết vấn đề gì?

Trong Java, **JVM biết về một lớp** không nhất thiết đồng nghĩa với việc **lớp đó đã được khởi tạo**. Ba trường hợp hay gây nhầm lẫn là:

1. Truy cập **class literal** như `Example.class`.
2. Tạo **mảng có kiểu phần tử là lớp** như `new Example[5]`.
3. Đọc **hằng có thể xác định lúc biên dịch** như `Example.MAX_SIZE` nếu đó là *constant variable* đúng nghĩa.

**Cả ba thao tác trên, xét riêng bản thân chúng, đều không kích hoạt initialization của `Example`.** Tuy vậy, JVM vẫn có thể đã load/link `Example`. Và nếu một biểu thức liên quan thực hiện thêm thao tác “active use” (chẳng hạn `new Example()` hoặc đọc một trường `static` không phải hằng), lớp vẫn có thể được khởi tạo ngay lúc đó.

Mục tiêu sau bài: nhận diện đúng ba trường hợp không kích hoạt, phân biệt `static final` với **constant variable**, dự đoán được output của ví dụ Java 17+ và không nhầm **loading** với **initialization**.

## 2. Nền tảng: loading, linking và initialization khác nhau

Khi JVM làm việc với một kiểu:

- **Loading:** tìm/định nghĩa biểu diễn runtime của lớp từ dữ liệu lớp. Một đối tượng `Class<?>` tương ứng có thể được JVM sử dụng.
- **Linking:** xác minh (`verification`), chuẩn bị (`preparation`), giải quyết tham chiếu biểu tượng (`resolution`). Một số việc phân giải có thể xảy ra muộn.
- **Initialization:** thực thi logic khởi tạo biến `static` và các khối `static {}` của lớp theo quy tắc Java/JVM.

Ví dụ mã minh họa:

~~~java
class Sample {
    static {
        System.out.println("Sample initialized");
    }
}
~~~

Nhìn thấy `Sample.class` hoặc thấy JVM đã nạp bytecode chưa đủ để kết luận `Sample initialized` đã được in. Chỉ khi `Sample` được **khởi tạo** thì khối `static` nói trên mới được thực thi; trong một định nghĩa lớp đã khởi tạo bình thường, khối này không chạy lại mỗi lần truy cập.

Theo [JLS 12.4.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.1), một lớp thường bị kích hoạt khởi tạo khi lần đầu có thao tác như:

- `new Sample()`: tạo **instance** `Sample`.
- `Sample.run()`: gọi phương thức `static` **thực sự được khai báo bởi `Sample`**.
- Gán một trường `static` được khai báo bởi `Sample`.
- Đọc một trường `static` được khai báo bởi `Sample` **nếu đó không phải constant variable**.
- Một số cơ chế đặc biệt/reflection, ví dụ overload `Class.forName(String)` yêu cầu initialization.

Khi lớp con được khởi tạo, superclass của nó cũng phải được khởi tạo theo quy tắc. Với trường tĩnh kế thừa, phải quan tâm **lớp khai báo trường**, chứ không chỉ tên lớp ghi bên trái dấu chấm.

**Giới hạn chính xác của bài:** “Không kích hoạt” chỉ có nghĩa **thao tác đang xét không tự yêu cầu khởi tạo lớp đích**. Nó không chứng minh lớp chưa được load/link, chưa từng được khởi tạo trước đó, hoặc không có lớp khác được khởi tạo như hệ quả của việc tính toán biểu thức.

## 3. Class literal: `Sample.class` không khởi tạo `Sample`

### 3.1. Lấy metadata không phải tạo instance

~~~java
Class<Sample> info = Sample.class;
System.out.println(info.getName());
~~~

`Sample.class` là **class literal**: nó cung cấp một đối tượng `Class<Sample>` mô tả kiểu. Thao tác này **không tự kích hoạt** khối `static {}` của `Sample`. Việc in tên qua metadata cũng không buộc phải khởi tạo `Sample`.

So sánh:

~~~java
Sample object = new Sample(); // kích hoạt khởi tạo Sample nếu chưa xảy ra
~~~

`new Sample()` tạo instance; đây là một trong các thao tác active use. Khác biệt nằm ở **lấy metadata** và **tạo đối tượng của lớp**.

### 3.2. Bảng phân biệt các biểu thức gần giống

| Biểu thức | Có tự yêu cầu khởi tạo lớp `Sample`? | Lý do |
|---|---|---|
| `Sample.class` | **Không** | Class literal chỉ tham chiếu metadata về kiểu |
| `Sample[].class` | **Không** | Class literal cho kiểu mảng, không tạo instance `Sample` |
| `Class.forName("Sample", false, loader)` | **Không yêu cầu** | `false` nói rõ không yêu cầu initialization |
| `Class.forName("Sample")` | **Có** | Overload một tham số yêu cầu initialization |
| `Class.forName("Sample", true, loader)` | **Có** | Cờ `true` yêu cầu initialization |
| `new Sample()` | **Có** | Tạo instance |
| `Sample.action()` nếu `action` là static method khai báo ở `Sample` | **Có** | Gọi phương thức static của lớp |

Với lớp có package, `Class.forName` cần **binary name** phù hợp, ví dụ `com.example.Sample`. Với lớp lồng tĩnh, tên nhị phân dùng `$`. Trong khi đó, `Sample.class` được compiler hiểu trực tiếp từ mã nguồn.

### 3.3. Chỗ dễ suy luận sai

- **“`Sample.class` chưa chạy `static`, vậy chưa load.”** Không có cơ sở. Loading và initialization là hai việc khác nhau.
- **“Có một đối tượng `Class<?>` là đã có instance `Sample`.”** Sai. `Class<?>` đại diện metadata của kiểu, không phải instance mà `new Sample()` tạo ra.
- **“`Class.forName` lúc nào cũng chỉ load.”** Sai: overload và cờ `initialize` quyết định yêu cầu initialization. Đừng dùng `Class.forName("Sample")` để minh họa trường hợp *không* khởi tạo.

## 4. Tạo mảng không đồng nghĩa khởi tạo lớp phần tử

### 4.1. Một mảng chỉ cấp chỗ chứa tham chiếu

~~~java
Sample[] samples = new Sample[3];
System.out.println(samples.length); // 3
~~~

Biểu thức `new Sample[3]` tạo **một đối tượng mảng** gồm ba vị trí tham chiếu, tất cả ban đầu đều là `null`:

~~~text
samples: Sample[]
+-----------+-----------+-----------+
| null      | null      | null      |
+-----------+-----------+-----------+
     [0]         [1]         [2]
~~~

Nó **không** gọi `new Sample()` ba lần. Vì vậy, tạo mảng không tự kích hoạt initialization của lớp thành phần `Sample`.

Tương tự, hai biểu thức sau không tự khởi tạo lớp `Sample`:

~~~java
Sample[][] grid = new Sample[2][3];
Class<?> arrayType = Sample[].class;
~~~

JVM có thể tạo hoặc tìm runtime class cho kiểu mảng và thông tin lớp phần tử, nhưng đó không phải khởi tạo `Sample`. Không nên lấy thời điểm array class được tạo để suy ra thời điểm khối `static {}` của `Sample` chạy.

### 4.2. Khi có instance trong biểu thức tạo mảng

~~~java
Sample[] refs = new Sample[2];               // không khởi tạo Sample
Sample[] withObject = {new Sample(), null};  // khởi tạo Sample
~~~

Trong dòng thứ hai, **`new Sample()`** là thao tác kích hoạt, không phải dấu ngoặc của array initializer.

Tương tự:

~~~java
Sample[] data = new Sample[Sample.size()];
~~~

Nếu `size()` là phương thức static khai báo bởi `Sample`, việc gọi `Sample.size()` có thể kích hoạt initialization trước khi mảng được cấp phát. **Đánh giá các biểu thức bên trong câu lệnh** phải được tách khỏi quy tắc khởi tạo do chính `new Sample[...]`.

### 4.3. Cách tự quan sát

Đặt `System.out.println("INIT Sample")` trong `static {}` của `Sample`. Chạy một JVM mới và thực hiện **chỉ** `Sample[] a = new Sample[2];`, in `a.length`; dự đoán không thấy `INIT Sample`. Sau đó thêm `a[0] = new Sample();`: khi chưa có hoạt động khởi tạo nào trước đó, dòng `INIT Sample` xuất hiện lúc tạo instance.

## 5. Đọc hằng biên dịch không khởi tạo lớp khai báo

### 5.1. Định nghĩa đúng của constant variable

Không phải bất kỳ `static final` nào cũng là hằng biên dịch. Theo [JLS 4.12.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4), một **constant variable** phải đồng thời:

1. Là biến có `final`.
2. Có kiểu **primitive** như `int`, `boolean`, `long`, `char` hoặc **`String`**.
3. Được gán giá trị bằng **constant expression** (xem [JLS 15.29](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29)).

Trong thực tế, ta thường gặp **`static final` constant variable** được công khai trong một lớp hoặc interface. Compiler có thể nhúng trực tiếp giá trị tại vị trí sử dụng; đọc trường hằng này không tự kích hoạt initializer của lớp khai báo.

~~~java
class Limits {
    static {
        System.out.println("INIT Limits");
    }

    static final int MAX = 2 + 3;           // constant variable
    static final String PREFIX = "ja" + "va"; // constant variable
}
~~~

`System.out.println(Limits.MAX)` sẽ in `5`; `System.out.println(Limits.PREFIX)` sẽ in `java`. Chỉ riêng hai lần đọc constant variable **không** khiến `INIT Limits` xuất hiện.

### 5.2. So sánh từng loại static field

| Khai báo trường tại `Limits` | Constant variable? | Đọc trường có tự kích hoạt `Limits`? |
|---|---|---|
| `static final int MAX = 5;` | Có | **Không** |
| `static final long MASK = 1L << 3;` | Có | **Không** |
| `static final String CODE = "A" + "B";` | Có | **Không** |
| `static final boolean READY = true;` | Có | **Không** |
| `static final Integer BOXED = 5;` | **Không** — `Integer` là reference type | **Có** |
| `static final int DYNAMIC = Integer.parseInt("5");` | **Không** — method call không phải constant expression | **Có** |
| `static final String UUID = System.getProperty("id");` | **Không** — method call | **Có** |
| `static final String X = new String("x");` | **Không** — `new` không phải constant expression | **Có** |
| `static final int[] VALUES = {1, 2};` | **Không** — kiểu mảng | **Có** |
| `static int mutable = 5;` | **Không** — không có `final` | **Có** |

Đừng nhầm “được gán một lần”, “giá trị cố định trong ví dụ” hoặc “có modifier `final`” với định nghĩa *constant variable*.

### 5.3. Interface và trường khai báo tại superclass

Một trường khai báo trong interface được ngầm định là `public static final`, nhưng chỉ là *constant variable* nếu giá trị là constant expression:

~~~java
interface Options {
    int PORT = 8080;                           // constant variable
    String MODE = System.getProperty("mode");   // không là constant variable
}
~~~

Đọc `Options.PORT` không tự khởi tạo `Options`; đọc `Options.MODE` là active use của một nonconstant static field và có thể kích hoạt khởi tạo interface.

Với kế thừa:

~~~java
class Parent {
    static int count = 1;
}
class Child extends Parent {}
~~~

Viết `Child.count` thực ra là tham chiếu trường **được khai báo bởi `Parent`**. Nếu chưa được khởi tạo, thao tác đọc nonconstant field này khởi tạo `Parent`; không vì cách viết `Child.count` mà tự động khởi tạo `Child`.

### 5.4. Rủi ro khi thay đổi public compile-time constant

Nếu thư viện xuất bản:

~~~java
public static final int API_VERSION = 1;
~~~

client đã biên dịch có thể lưu trực tiếp literal `1` vào bytecode. Sau này thư viện đổi trường thành `2` nhưng client **chưa được biên dịch lại**: client vẫn có thể in `1` ngay cả khi đang dùng JAR thư viện mới.

Đây là hệ quả của **compile-time inlining** và binary compatibility ([JLS 13.4.9](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.9)), không phải ClassLoader “giữ nhầm giá trị”. Khi thay hằng công khai có client phụ thuộc, kiểm tra và biên dịch lại client khi cần.

## 6. Thực hành Java 17+ chạy độc lập

Tạo đúng tệp **`NoInitTriggersDemo.java`**. Mọi lớp cần thiết đều nằm trong một tệp:

~~~java
public class NoInitTriggersDemo {
    static class FromLiteral {
        static { System.out.println("INIT FromLiteral"); }
    }

    static class ArrayElement {
        static { System.out.println("INIT ArrayElement"); }
    }

    static class CompileTimeConstants {
        static { System.out.println("INIT CompileTimeConstants"); }
        static final int RETRIES = 2 + 3;
        static final String MODE = "safe";
        static final Integer BOXED = 10;
    }

    static class ComputedValue {
        static { System.out.println("INIT ComputedValue"); }
        static final int COUNT = Integer.parseInt("9");
    }

    public static void main(String[] args) {
        System.out.println("A");
        Class<?> type = FromLiteral.class;
        System.out.println(type.getSimpleName());

        System.out.println("B");
        ArrayElement[] array = new ArrayElement[3];
        System.out.println(array.length);

        System.out.println("C");
        System.out.println(CompileTimeConstants.RETRIES);
        System.out.println(CompileTimeConstants.MODE);

        System.out.println("D");
        System.out.println(ComputedValue.COUNT);

        System.out.println("E");
        System.out.println(CompileTimeConstants.BOXED);

        System.out.println("F");
        new FromLiteral();
        new ArrayElement();
    }
}
~~~

Biên dịch/chạy từ thư mục chứa tệp:

~~~sh
javac NoInitTriggersDemo.java
java NoInitTriggersDemo
~~~

**Stdout chính xác** (đã kiểm tra bằng `javac --release 17`):

~~~text
A
FromLiteral
B
3
C
5
safe
D
INIT ComputedValue
9
E
INIT CompileTimeConstants
10
F
INIT FromLiteral
INIT ArrayElement
~~~

### Giải thích đúng điểm khởi tạo

| Nhóm dòng | Thao tác | Vì sao chưa/đã khởi tạo |
|---|---|---|
| `A → FromLiteral` | `FromLiteral.class` và đọc tên metadata | Chưa có active use khiến `FromLiteral` initialization |
| `B → 3` | `new ArrayElement[3]` | Tạo mảng `null`; không tạo `ArrayElement` |
| `C → 5 / safe` | Đọc `RETRIES` và `MODE` | Hai trường là constant variables nên không tự khởi tạo `CompileTimeConstants` |
| `D → INIT ComputedValue → 9` | Đọc `COUNT` | `Integer.parseInt` khiến `COUNT` không là constant variable; `getstatic` kích hoạt khởi tạo |
| `E → INIT CompileTimeConstants → 10` | Đọc `BOXED` | `Integer` là reference type, do đó `BOXED` không là constant variable |
| `F → INIT FromLiteral / INIT ArrayElement` | Hai biểu thức `new` | Tạo instance của mỗi lớp, kích hoạt initialization nếu lớp chưa init |

Quan sát quan trọng nhất là `INIT CompileTimeConstants` **không xuất hiện khi đọc hai hằng `RETRIES`/`MODE`**, mà chỉ xuất hiện khi đọc `BOXED`. `FromLiteral` cũng chỉ init khi tạo instance ở nhóm `F`, dù `FromLiteral.class` đã được lấy từ nhóm `A`.

### Kiểm chứng ở mức bytecode

~~~sh
javap -c -p NoInitTriggersDemo
~~~

Hãy tìm trong phương thức `main`:

- `ldc` cho class literal và literal chuỗi.
- `anewarray` cho thao tác cấp phát mảng tham chiếu.
- Giá trị `RETRIES` và `MODE` được dùng trực tiếp tại vị trí gọi; không cần `getstatic` của hai constant variables đó.
- `getstatic` đối với `ComputedValue.COUNT` và `CompileTimeConstants.BOXED`.

Các opcode quan sát với `javac` giúp hiểu lý do code hoạt động; **đặc tả JLS** mới là nguồn quy tắc về thời điểm initialization. Không kết luận mọi chi tiết JVM từ một opcode đơn lẻ.

## 7. Thực nghiệm nhỏ để phân biệt nguyên nhân

**Thí nghiệm 1 — Mảng có phần tử khởi tạo ngay:** đổi `new ArrayElement[3]` thành `new ArrayElement[]{new ArrayElement(), null, null}`. Dòng `INIT ArrayElement` chuyển lên nhóm `B`, vì đã có `new ArrayElement()` trong biểu thức phần tử.

**Thí nghiệm 2 — Đổi nonconstant thành constant:** đổi `static final int COUNT = Integer.parseInt("9");` thành `static final int COUNT = 9;` rồi **biên dịch lại**. Lần đọc `COUNT` không còn tự kích hoạt initializer; `INIT ComputedValue` biến mất khỏi chương trình này.

**Thí nghiệm 3 — Chỉ thay `class literal` bằng instance:** giữ `FromLiteral.class`, thêm `new FromLiteral();` ngay bên dưới. Lớp `FromLiteral` được khởi tạo tại dòng tạo instance đó; class literal vẫn không phải tác nhân kích hoạt.

**Thí nghiệm 4 — Reflection:** so `Class.forName("NoInitTriggersDemo$FromLiteral", false, loader)` với cờ `true` (nơi `loader` là defining loader của `NoInitTriggersDemo`). Overload cờ `false` không yêu cầu initialization; cờ `true` yêu cầu. Hãy đặt phép thử trước mọi `new FromLiteral()` để quan sát khác biệt.

**Lưu ý quan sát:** khởi chạy **JVM mới** cho mỗi trường hợp cần trạng thái lớp chưa khởi tạo. Việc lặp lại các phép thử trong cùng JVM sau khi đã init không làm `static {}` in lần nữa, dễ gây kết luận sai.

## 8. Những nhầm lẫn cần tránh

1. **“Không init” nghĩa là “không load”.** Sai: class literal và array allocation có thể buộc JVM làm việc với thông tin lớp mà không khởi tạo lớp đích.
2. **“`new Sample[3]` tạo ba `Sample`.”** Sai: nó chỉ tạo một mảng ba slot `null`.
3. **“Mảng chứa `new Sample()` nên bản thân việc tạo mảng gây init.”** Sai: chính phép tạo **instance** gây init.
4. **“`final` hoặc `static final` nào cũng được inline.”** Sai: primitive/`String` và constant expression là các tiêu chí bắt buộc.
5. **“`Integer` là số, vì vậy `static final Integer` là constant variable.”** Sai: `Integer` là reference type.
6. **“Tên bên trái dấu chấm quyết định chính xác lớp phải khởi tạo.”** Sai với trường kế thừa; cần nhìn lớp thực sự **khai báo** trường.
7. **“Interface field đều không kích hoạt khởi tạo.”** Sai: một interface field không phải constant variable có thể khiến interface được khởi tạo khi đọc.
8. **“`Class.forName` luôn giống `Target.class`.”** Sai: overload một tham số yêu cầu initialization.
9. **“Không thấy log initializer tức lớp chưa từng init.”** Sai nếu lớp đã init trước đó; phải quan sát trên JVM mới và gắn log cho đúng lớp.
10. **“Đổi giá trị constant trong JAR thì mọi client tự nhận giá trị mới.”** Sai nếu client đã inline và chưa được biên dịch lại.

## 9. Câu hỏi ôn tập

1. Nêu sự khác nhau giữa loading, linking và initialization. Vì sao `Sample.class` không chứng minh khối `static {}` đã chạy?
2. Vì sao `new Sample[4]` không tạo bốn đối tượng `Sample`?
3. Trong `Sample[] data = {new Sample()};`, thao tác nào gây initialization?
4. Phân loại `static final int A = 5;`, `static final int B = parse();` và `static final Integer C = 5;` thành constant/nonconstant variables.
5. Khi đọc `Child.X` nhưng `X` là nonconstant static field khai báo ở `Parent`, lớp nào là đối tượng của trigger?
6. Đọc `Options.PORT` và `Options.MODE` ở interface tại mục 5 khác nhau thế nào?
7. Vì sao `INIT CompileTimeConstants` xuất hiện ở nhóm `E` mà không xuất hiện ở nhóm `C` của chương trình?
8. Trong trường hợp nào `Class.forName(name, false, loader)` phù hợp hơn `Class.forName(name)` để chỉ quan sát việc tìm lớp?
9. Một chương trình đã in `INIT Sample`, sau đó chạy lại `new Sample()` nhưng không in tiếp: điều này có bình thường không?
10. Vì sao đổi một public compile-time constant ở thư viện có thể cần biên dịch lại client?

**Hoàn thành bài khi:** dự đoán đúng stdout, giải thích được ba thao tác không kích hoạt initialization và phân biệt được *constant variable* với các trường `static final` không phải hằng biên dịch.

## 10. Tài liệu chuẩn

- [JLS Java SE 21 12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.1): các trigger của initialization, ví dụ superclass, static fields và interface.
- [JLS Java SE 21 4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4): định nghĩa của constant variable.
- [JLS Java SE 21 15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29): biểu thức hằng hợp lệ.
- [JLS Java SE 21 13.4.9 — final Fields and Constants](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.9): hệ quả biên dịch khi giá trị hằng thay đổi.
- [Java SE 21 Class.forName API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): tham số `initialize`.

Ví dụ dùng API và cú pháp tương thích Java 17 trở lên; quy tắc về thời điểm khởi tạo được trình bày theo Java Language Specification.