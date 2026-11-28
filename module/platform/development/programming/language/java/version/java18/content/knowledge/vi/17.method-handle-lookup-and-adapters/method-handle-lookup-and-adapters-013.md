# guardWithTest(): chọn nhánh thực thi và kiểm tra tương thích kiểu giữa test và các nhánh

> **Phạm vi bài học:** Chương **Lookup và adapter** thuộc module `JAVA_VERSION_JAVA18`. Java 18 có JEP 416 tái triển khai core reflection trên nền method handles; riêng `java.lang.invoke.MethodHandles.guardWithTest` là API công khai vẫn áp dụng trên các JDK hiện đại. Bài giải thích cách kết hợp một phép kiểm tra kiểu `boolean` với hai nhánh thực thi, quy tắc bắt buộc của `MethodType` và cách dùng adapter để nối các handle có chữ ký khác nhau. Ví dụ chỉ sử dụng API Java SE được hỗ trợ, không phụ thuộc lớp nội bộ hoặc hành vi legacy.

## 1. `guardWithTest` giải quyết vấn đề gì?

Trong Java thông thường, ta có thể chọn một trong hai nhánh:

~~~java
String output;
if (amount >= 0) {
    output = accept(amount, source);
} else {
    output = reject(amount, source);
}
~~~

Nếu hệ thống dùng `MethodHandle` để dựng một pipeline động (chẳng hạn một bộ chuyển đổi dữ liệu hoặc bộ định tuyến lời gọi), ta có thể mô tả **cả điều kiện lẫn hai nhánh bằng handle**:

~~~java
MethodHandle guarded =
        MethodHandles.guardWithTest(test, target, fallback);
~~~

Khi `guarded` được gọi:

1. Nó truyền các đối số cần thiết cho `test`.
2. `test` trả `true` thì `target` được gọi; trả `false` thì `fallback` được gọi.
3. Nhánh được chọn nhận bộ đối số thích hợp của lời gọi `guarded` và cung cấp kết quả.
4. Kết quả được trả về theo kiểu trả về chung của hai nhánh.

Sơ đồ:

~~~text
guarded(args...)
       |
       v
   test(args-prefix) -- trả boolean
       |
  +----+----+
  |         |
 true      false
  |         |
  v         v
target    fallback
  |         |
  +----+----+
       |
       v
   giá trị trả về
~~~

**Chỉ một nhánh được chọn và thực thi cho mỗi lần gọi thành công qua test.** Nếu test ném ngoại lệ, hai nhánh không được gọi. Điều kiện ở đây là một **method handle có type trả về `boolean`**, không phải một object kiểu `Predicate` tự động được nhận vào `guardWithTest`.

### Khi nào nên dùng?

- Xây dựng dispatch giữa một fast path và fallback theo trạng thái hoặc dạng dữ liệu.
- Chọn bộ xử lý dựa trên một điều kiện có thể diễn đạt bằng method handle.
- Kết hợp các adapter của `java.lang.invoke` thành một handle có chữ ký cố định để cache và tái sử dụng.
- Tách việc chọn đường thực thi khỏi phần code gọi, khi các bước đã được biểu diễn bằng handle.

Đối với điều kiện nghiệp vụ đơn giản và tĩnh, `if/else` thông thường thường rõ ràng hơn. `guardWithTest` đặc biệt hữu ích khi đang **kết hợp các handle động** và muốn có một handle duy nhất để gọi tiếp.

## 2. Hợp đồng kiểu của ba handle

Khai báo API:

~~~java
public static MethodHandle guardWithTest(
        MethodHandle test,
        MethodHandle target,
        MethodHandle fallback)
~~~

Trước khi tạo một handle mới, phải xác minh:

| Thành phần | Quy tắc cần thỏa |
|---|---|
| `test` | Có kiểu trả về **primitive `boolean`** |
| Tham số của `test` | Là một **phần đầu (prefix)** của danh sách kiểu tham số trên `target` và `fallback`; được phép ít tham số hơn |
| `target` và `fallback` | Có **MethodType bằng nhau**, gồm **toàn bộ tham số và kiểu trả về** |
| Handle được tạo | Có **cùng MethodType** với `target` và `fallback` |

Với hai nhánh có chữ ký:

~~~text
target.type()   = (int, String)String
fallback.type() = (int, String)String
~~~

Các test sau là hợp lệ:

~~~text
test A: (int, String)boolean  // dùng đủ hai đối số
test B: (int)boolean          // dùng tham số đầu
test C: ()boolean             // không cần đối số
~~~

Nhưng các test sau không phù hợp:

~~~text
test X: (String)boolean       // không trùng prefix: đối số đầu phải là int
test Y: (int, long)boolean    // vị trí thứ hai sai kiểu
test Z: (int, String)Boolean  // wrapper Boolean không phải primitive boolean
test W: (int, String, int)boolean // có nhiều tham số hơn hai nhánh
~~~

**Không có overload resolution hay tự sắp xếp đối số.** Quy tắc prefix dựa vào **đúng vị trí và đúng kiểu khai báo** của `MethodType`. Ví dụ nếu test chỉ cần đối số thứ hai kiểu `String`, nó **không thể** dùng chữ ký `(String)boolean` trực tiếp để kiểm tra đối số thứ hai của nhánh `(int, String)String`. Ta phải dùng adapter thích hợp, như `dropArguments`, để biến test thành `(int, String)boolean`.

### Kiểm tra bằng `MethodType`

~~~java
MethodType targetType = target.type();
MethodType fallbackType = fallback.type();
MethodType testType = test.type();

if (!targetType.equals(fallbackType)) {
    throw new IllegalArgumentException("Branch types differ");
}
if (testType.returnType() != boolean.class) {
    throw new IllegalArgumentException("Test must return boolean");
}
if (testType.parameterCount() > targetType.parameterCount()) {
    throw new IllegalArgumentException("Too many test parameters");
}
for (int i = 0; i < testType.parameterCount(); i++) {
    if (testType.parameterType(i) != targetType.parameterType(i)) {
        throw new IllegalArgumentException(
                "Test parameter does not match prefix at " + i);
    }
}
~~~

Đoạn minh họa giả định đã khai báo `test`, `target` và `fallback`. So sánh đối tượng `Class<?>` bằng `!=` ở đây phù hợp vì ta đối chiếu chính các kiểu được lưu trong `MethodType`. Kiểm tra thủ công giúp báo lỗi cấu hình dễ hiểu; chính `guardWithTest` cũng kiểm tra hợp đồng và từ chối tổ hợp không phù hợp.

## 3. Ví dụ đầy đủ: chọn nhánh theo dấu của số nguyên

Tạo file `GuardWithTestDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class GuardWithTestDemo {

    // Test chỉ cần tham số đầu: (int)boolean
    public static boolean nonNegative(int amount) {
        return amount >= 0;
    }

    // Hai nhánh có cùng chữ ký: (int, String)String
    public static String accept(int amount, String source) {
        return source + ":accepted:" + amount;
    }

    public static String reject(int amount, String source) {
        return source + ":rejected:" + amount;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle test = lookup.findStatic(
                GuardWithTestDemo.class,
                "nonNegative",
                MethodType.methodType(boolean.class, int.class)
        );

        MethodType branchType = MethodType.methodType(
                String.class, int.class, String.class
        );

        MethodHandle target = lookup.findStatic(
                GuardWithTestDemo.class, "accept", branchType
        );
        MethodHandle fallback = lookup.findStatic(
                GuardWithTestDemo.class, "reject", branchType
        );

        System.out.println("test:     " + test.type());
        System.out.println("target:   " + target.type());
        System.out.println("fallback: " + fallback.type());

        MethodHandle guarded =
                MethodHandles.guardWithTest(test, target, fallback);
        System.out.println("guarded:  " + guarded.type());

        String yes = (String) guarded.invokeExact(8, "API");
        String no = (String) guarded.invokeExact(-3, "CLI");

        System.out.println(yes);
        System.out.println(no);
    }
}
~~~

Biên dịch và chạy với một JDK hiện đại (JDK 18 trở lên):

~~~shell
javac -encoding UTF-8 GuardWithTestDemo.java
java GuardWithTestDemo
~~~

Kết quả mong đợi:

~~~text
test:     (int)boolean
target:   (int,String)String
fallback: (int,String)String
guarded:  (int,String)String
API:accepted:8
CLI:rejected:-3
~~~

### Đọc kết quả

- `findStatic` tạo handle cho các phương thức static; không có receiver ngầm trong `MethodType`.
- `test.type()` là `(int)boolean`, tức test chỉ nhận đối số `amount`.
- Cả hai nhánh có `(int,String)String`. Khi test nhận một đối số, `source` **không được truyền cho test**, nhưng vẫn truyền cho nhánh được chọn.
- `guarded.type()` bằng type của nhánh, không phải type của test.
- `invokeExact` yêu cầu kiểu call site trùng chữ ký: đối số thứ nhất là `int`, đối số thứ hai là `String` và kiểu kết quả là `String`.

**Tại sao cần cast `(String)` trước `invokeExact`?** Kiểu trả về là một phần của chữ ký call site trong lời gọi signature-polymorphic. Không nên để ngữ cảnh vô tình yêu cầu kiểu trả về `Object` hoặc `void` nếu handle có type trả về `String`.

## 4. Test được phép nhận ít tham số hơn hai nhánh

Khả năng dùng **prefix** giúp tránh việc tạo adapter khi test chỉ cần vài tham số đầu.

Ví dụ:

~~~text
test.type()      = (int)boolean
target.type()    = (int,String)String
fallback.type()  = (int,String)String

guarded.type()   = (int,String)String
~~~

Khi gọi `guarded.invokeExact(8, "API")`:

1. Test chỉ nhận `8`.
2. Vì `8 >= 0`, nhánh `target` nhận **cả** `8` và `"API"`.
3. Nhánh fallback không được gọi.

Trường hợp test **không cần đối số nào** cũng hợp lệ, ví dụ một handle `()boolean` đọc trạng thái runtime. Khi đó kết quả test vẫn quyết định nhánh cho từng invocation, còn các đối số ban đầu được chuyển đến nhánh tương ứng.

**Lưu ý:** Test thiếu tham số **ở cuối** danh sách, không được tự chọn bỏ qua một tham số ở giữa rồi coi phần còn lại là prefix. Nếu muốn kiểm tra tham số nằm sau, hãy biến đổi type của test bằng adapter.

## 5. Dùng adapter để test kiểm tra tham số ở vị trí khác

Giả sử test thực sự quan tâm đến `source` (tham số thứ hai của hai nhánh), thay vì `amount` (tham số đầu). Ta có phương thức:

~~~java
public static boolean fromApi(String source) {
    return "API".equals(source);
}
~~~

Handle gốc `fromApi` có type `(String)boolean`. Nó không khớp phần đầu của `(int,String)String`. Có thể dùng:

~~~java
MethodHandle sourceTest = lookup.findStatic(
        GuardWithTestDemo.class,
        "fromApi",
        MethodType.methodType(boolean.class, String.class)
);

MethodHandle alignedTest = MethodHandles.dropArguments(
        sourceTest,
        0,
        int.class
);
// sourceTest:  (String)boolean
// alignedTest: (int,String)boolean

MethodHandle choose =
        MethodHandles.guardWithTest(alignedTest, target, fallback);
~~~

Đoạn minh họa giả định `lookup`, `target` và `fallback` như ở ví dụ trước, và đã thêm phương thức `fromApi` vào lớp `GuardWithTestDemo`. `dropArguments(sourceTest, 0, int.class)` **thêm một tham số đầu kiểu `int` vào chữ ký adapter và bỏ qua giá trị này** khi gọi test gốc.

Lúc này `alignedTest` nhận cùng hai tham số với nhánh, nhưng chỉ truyền `source` cho `fromApi`. Đây là cách thích nghi đúng ý nghĩa, thay vì cố đưa `(String)boolean` trực tiếp vào `guardWithTest`.

Có thể dùng các adapter khác để sắp xếp tham số khi cần, chẳng hạn `permuteArguments`, nhưng phải ghi rõ mapping các vị trí và kiểm tra `type()` của handle sau khi biến đổi.

### Dùng test không đối số

~~~java
MethodHandle alwaysTrue =
        MethodHandles.constant(boolean.class, true);
// alwaysTrue.type() == ()boolean

MethodHandle choose =
        MethodHandles.guardWithTest(alwaysTrue, target, fallback);
~~~

Cấu hình này hợp lệ vì danh sách tham số rỗng là prefix của mọi danh sách. Nó sẽ chọn `target` trong mọi lần gọi. Ví dụ chỉ minh họa luật prefix; trong ứng dụng thật, test thường phụ thuộc dữ liệu hoặc trạng thái cần đánh giá.

## 6. Chuẩn hóa hai nhánh có chữ ký khác nhau

Hai nhánh **phải có `MethodType` giống nhau** trước khi đưa vào `guardWithTest`. Không thể nhờ hàm tổ hợp tự padding hoặc chuyển đổi kiểu khi dựng guard.

### 6.1. Nhánh thiếu một tham số: `dropArguments`

Giả sử fallback chỉ cần một số nguyên:

~~~java
public static String rejectWithoutSource(int amount) {
    return "rejected:" + amount;
}
~~~

Handle của phương thức này có type `(int)String`, trong khi nhánh `target` có `(int,String)String`. Thích nghi:

~~~java
MethodHandle shortFallback = lookup.findStatic(
        GuardWithTestDemo.class,
        "rejectWithoutSource",
        MethodType.methodType(String.class, int.class)
);

MethodHandle fullFallback = MethodHandles.dropArguments(
        shortFallback,
        1,
        String.class
);
// (int)String -> (int,String)String

MethodHandle guarded =
        MethodHandles.guardWithTest(test, target, fullFallback);
~~~

`dropArguments` thêm tham số `String` ở vị trí 1 của handle mới. Đối số đó bị bỏ qua khi gọi fallback gốc; vì vậy cả hai nhánh có thể nhận cùng signature mà vẫn giữ logic cũ.

### 6.2. Nhánh khác kiểu tham số: `asType` nếu hợp đồng chuyển đổi cho phép

Giả sử có nhánh fallback nhận wrapper:

~~~java
public static String rejectBoxed(Integer amount, String source) {
    return source + ":boxed-rejected:" + amount;
}
~~~

Handle gốc có type `(Integer,String)String`. Ta có thể chủ động chọn việc boxing `int` thành `Integer` bằng `asType`:

~~~java
MethodHandle boxedFallback = lookup.findStatic(
        GuardWithTestDemo.class,
        "rejectBoxed",
        MethodType.methodType(
                String.class, Integer.class, String.class)
);

MethodHandle adaptedFallback =
        boxedFallback.asType(target.type());
// (Integer,String)String -> (int,String)String

MethodHandle guarded =
        MethodHandles.guardWithTest(test, target, adaptedFallback);
~~~

Vì `asType` có thể tạo adapter từ đối số `int` sang `Integer`, lúc này hai nhánh cùng có type `(int,String)String`. Đây là **chuyển đổi có chủ đích** và làm thay đổi đường truyền giá trị; nó có thể tạo thêm boxing. Không khẳng định adapter luôn rẻ hay miễn phí; với đường nóng, hãy đo trên workload thực.

**Không phải mọi tổ hợp kiểu đều có adapter hợp lệ.** Chẳng hạn chuyển kết quả primitive `int` thành `boolean` không thuộc các chuyển đổi mà `asType` hỗ trợ. Nếu không thể thích nghi, việc tạo adapter có thể ném `WrongMethodTypeException`. Cần sửa thiết kế chữ ký hoặc cung cấp bước chuyển đổi được định nghĩa rõ ràng.

### 6.3. Khác kiểu trả về

Nếu `target` trả `String` còn `fallback` trả `Object`, `guardWithTest` sẽ **không tự quy về kiểu chung**. Cần quyết định một chữ ký trả về chung và dùng adapter thích hợp trước khi tổ hợp, nếu quy tắc chuyển đổi của `asType` cho phép. Ví dụ, một nhánh trả `String` có thể thích nghi để trả `Object` bằng reference widening; tuy nhiên sau đó cả hai nhánh phải có cùng toàn bộ type.

Đừng tự suy đoán rằng `guardWithTest` biết chọn kiểu theo quan hệ kế thừa giữa các lớp. Nó chỉ nhận các handle đã thỏa hợp đồng chữ ký.

## 7. Phân biệt lỗi lúc tạo guard và lỗi lúc gọi guard

Đây là phần quan trọng để chẩn đoán đúng tầng.

### 7.1. Khi `guardWithTest` nhận ba handle không tương thích

Nếu `test` trả sai kiểu, không có prefix phù hợp, hoặc hai nhánh khác `MethodType`, lỗi xuất hiện **ngay khi tạo guard**.

Ví dụ test trả `int` thay cho primitive `boolean`:

~~~java
MethodHandle wrongTest = MethodHandles.identity(int.class);
// wrongTest.type() == (int)int

try {
    MethodHandles.guardWithTest(wrongTest, target, fallback);
    throw new AssertionError("Expected IllegalArgumentException");
} catch (IllegalArgumentException expected) {
    System.out.println("Test must return boolean");
}
~~~

Ví dụ fallback có kiểu trả về `int`, khác kiểu trả về `String` của target:

~~~java
MethodHandle intConstant = MethodHandles.constant(int.class, 0);
MethodHandle intFallback = MethodHandles.dropArguments(
        intConstant,
        0,
        int.class,
        String.class
);
// intFallback.type() == (int,String)int

try {
    MethodHandles.guardWithTest(test, target, intFallback);
    throw new AssertionError("Expected IllegalArgumentException");
} catch (IllegalArgumentException expected) {
    System.out.println("Branch types must match");
}
~~~

Các đoạn này dùng `test`, `target` và `fallback` trong ví dụ đầy đủ ở mục 3. Với các tổ hợp sai nêu trên, `guardWithTest` ném **`IllegalArgumentException` do quy tắc cấu trúc**, không phải lỗi do nhánh được chọn chạy.

### 7.2. Guard hợp lệ, nhưng gọi với call site sai kiểu

Giả sử `guarded.type()` là `(int,String)String`. Vì `MethodHandle.invokeExact` yêu cầu chữ ký call site khớp hoàn toàn:

~~~java
String valid = (String) guarded.invokeExact(1, "API");

long wrongNumber = 1L;
String invalid = (String) guarded.invokeExact(wrongNumber, "API");
// WrongMethodTypeException: call site (long,String)String
// khác guarded.type() (int,String)String.
~~~

`WrongMethodTypeException` trong ví dụ thứ hai phát sinh **lúc invocation** vì gọi `invokeExact` với signature không khớp. Nó khác với `IllegalArgumentException` khi **xây dựng guard** từ ba handle sai type.

Khi dùng `invoke` thay vì `invokeExact`, một số thích nghi kiểu có thể được thực hiện theo quy tắc `asType`; khi không thể chuyển đổi, `invoke` cũng có thể ném `WrongMethodTypeException`. Với một adapter hợp lệ, lỗi `ClassCastException` hoặc `NullPointerException` vẫn có thể xảy ra vì giá trị runtime không phù hợp.

### 7.3. Guard và các nhánh có thể tự ném ngoại lệ

- Nếu **test** ném exception, hai nhánh không được chọn.
- Nếu **target** được chọn và ném exception, fallback **không phải** cơ chế catch tự động. Exception của target được truyền cho caller.
- Nếu **fallback** được chọn và ném exception, target cũng không được chạy để “thử lại”.
- Khi cần cơ chế bắt và xử lý ngoại lệ thực sự bằng method handles, đó là một hợp đồng khác như `MethodHandles.catchException`; `guardWithTest` chỉ **chọn nhánh theo boolean**.

Method handles không tự bọc mọi exception của phương thức đích vào `InvocationTargetException` như `java.lang.reflect.Method.invoke`. Nếu ngoại lệ đến từ code nhánh, hãy phân tích source và stack trace của nhánh.

## 8. Test và nhánh phải thống nhất ngữ nghĩa, không chỉ kiểu

`guardWithTest` chỉ kiểm tra chữ ký, không biết test có thật sự đại diện cho lựa chọn nghiệp vụ hay không.

Chẳng hạn:

~~~java
static boolean validAmount(int amount) {
    return amount >= 0;
}

static String target(int amount, String source) {
    return "ok";
}

static String fallback(int amount, String source) {
    return "error";
}
~~~

Cả ba có thể tổ hợp hợp lệ, nhưng doanh nghiệp có thể yêu cầu `amount > 0` hoặc một logic phân quyền phức tạp hơn. Việc chữ ký khớp không đảm bảo **logic lựa chọn đúng**, cũng như không đảm bảo hai nhánh có cùng side effect.

### 8.1. Đầu vào được tính trước khi test chạy

Một hiểu lầm thường gặp: guard tránh tính cả các tham số vốn không được test sử dụng. Trong Java, biểu thức dùng làm đối số tại call site được đánh giá **trước khi** lời gọi handle bắt đầu:

~~~java
String result = (String) guarded.invokeExact(
        1,
        expensiveSource()
);
~~~

Ở đây `expensiveSource()` vẫn được thực thi để tạo `source`, dù `test` chỉ đọc `amount`. Guard quyết định **nhánh thực thi sau khi có đối số**, chứ không trì hoãn tự động việc đánh giá biểu thức đối số ở Java call site.

Nếu thực sự muốn trì hoãn một công việc tốn kém, cần thiết kế riêng dữ liệu đầu vào (ví dụ supplier) hoặc di chuyển phần việc đó vào nhánh được chọn.

### 8.2. Test có side effect

Một test handle có thể ghi state hoặc ném exception vì nó là một lời gọi thực thi. Nếu test thay đổi dữ liệu mà target/fallback phụ thuộc, phải định nghĩa rõ thứ tự và tính nhất quán. Không mặc định test là hàm thuần chỉ vì trả `boolean`.

### 8.3. Nhánh nào được gọi?

Trong một invocation bình thường, kết quả `boolean` của test chọn một trong hai nhánh. Vì cả hai nhánh có cùng type, chúng nhận các đối số theo cùng thứ tự và caller luôn quan sát cùng kiểu trả về ở lớp `MethodType`, dù giá trị và side effect có thể khác.

Điều này hữu ích khi xây pipeline nhưng không thay thế validation về nghiệp vụ, an toàn dữ liệu hay quyền truy cập vào thành viên mà `Lookup` tìm được.

## 9. `Lookup` và `guardWithTest` có trách nhiệm khác nhau

Một pipeline có thể tìm các handle bằng:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle target = lookup.findStatic(
        SomeClass.class,
        "targetMethod",
        MethodType.methodType(String.class, int.class)
);
~~~

`Lookup` kiểm tra quyền truy cập khi tìm thành viên; với `findVirtual` còn cần nhớ receiver xuất hiện ở vị trí đầu trong type của handle tìm được. `guardWithTest` **không nâng quyền** để tạo các handle mà caller không được phép lookup. Nó chỉ tổ hợp các handle **đã lấy được** theo hợp đồng type.

Ví dụ, một method handle cho instance method có type `(SomeClass,int)String`, còn một static fallback có type `(int)String` thì hai nhánh chưa tương thích. Có thể `bindTo` receiver để thu hẹp chữ ký hoặc `dropArguments` để thích nghi fallback nếu phù hợp ý nghĩa, rồi mới gọi `guardWithTest`.

Một trình tự đáng tin cậy:

1. Tìm handle bằng `Lookup` có quyền thích hợp.
2. In/kiểm tra `type()` của từng handle, gồm receiver và return type.
3. Chủ động dùng adapter khi chữ ký khác nhau.
4. Tạo guard từ test/target/fallback đã được kiểm tra.
5. Cache guard nếu tái sử dụng nhiều lần và không cần đổi cấu trúc pipeline.
6. Gọi qua `invokeExact` khi call site đã khớp chính xác; dùng `invoke` khi chủ đích cần adaptation được hỗ trợ.

Không dựa vào `setAccessible` hoặc API `jdk.internal.*` để ép quyền truy cập cho một handle không hợp lệ.

## 10. Bảng chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và sửa |
|---|---|---|
| `IllegalArgumentException` ngay tại `guardWithTest` | Test không trả primitive `boolean` | Xem `test.type().returnType()` |
| `IllegalArgumentException` khi tạo guard | Target và fallback khác type | So sánh `target.type().equals(fallback.type())` |
| `IllegalArgumentException` khi tạo guard | Tham số test không phải prefix của nhánh | So từng `parameterType(i)` với nhánh |
| `WrongMethodTypeException` tại `invokeExact` | Call site khác type của guard | Đối chiếu đối số **và kiểu trả về** |
| `WrongMethodTypeException` lúc `asType` | Chuyển đổi chữ ký không được hỗ trợ | Chọn adapter khác hoặc sửa chữ ký |
| `ClassCastException` khi đi qua adapter | Reference runtime không thuộc lớp yêu cầu | Kiểm tra giá trị runtime và type adapter |
| `NullPointerException` khi adapter/nhánh chạy | Unbox null, receiver null hoặc code đích dereference null | Phân tích đối số và stack trace |
| `NoSuchMethodException` tại `findStatic` hoặc `findVirtual` | Sai tên, tham số, return type hoặc nhầm static/instance | Kiểm tra chữ ký phương thức đích |
| `IllegalAccessException` ở `Lookup` | Caller không có quyền tạo handle | Kiểm tra quyền truy cập Java và module |
| Nhánh fallback không chạy khi target lỗi | Test đã trả `true`; guard không tự catch exception | Dùng error handling riêng nếu cần |
| Test chỉ có một tham số nhưng muốn đọc đối số thứ hai | Không khớp prefix | Dùng `dropArguments` hoặc adapter phù hợp |

### Cách lập một bảng type trước khi ghép

Trong các pipeline phức tạp, nên viết thành bảng nhỏ:

| Handle | Type ban đầu | Type muốn có | Adapter |
|---|---|---|---|
| Test kiểm tra source | `(String)boolean` | `(int,String)boolean` | `dropArguments(test, 0, int.class)` |
| Nhánh target | `(int,String)String` | `(int,String)String` | Không cần |
| Fallback bỏ qua source | `(int)String` | `(int,String)String` | `dropArguments(fallback, 1, String.class)` |
| Guard kết quả | — | `(int,String)String` | `guardWithTest(alignedTest,target,fullFallback)` |

Đặt type của từng handle trong log khi phát triển giúp phát hiện lỗi sớm hơn so với chỉ quan sát exception sau khi pipeline đã chạy.

## 11. Checklist triển khai

| Bước | Điều kiện xác nhận |
|---|---|
| 1. Xác định hai nhánh | Target và fallback biểu diễn đúng hai lựa chọn nghiệp vụ |
| 2. Kiểm tra return type test | `boolean.class`, không phải `Boolean.class` |
| 3. Kiểm tra tham số test | Trùng một **prefix** của tham số hai nhánh |
| 4. Kiểm tra type nhánh | `target.type().equals(fallback.type())` |
| 5. Thích nghi khi cần | Dùng `dropArguments`, `asType` hoặc adapter đúng ngữ nghĩa |
| 6. Kiểm tra type kết quả | `guarded.type()` trùng type của nhánh |
| 7. Gọi với đúng call site | `invokeExact` phải đúng tham số và kiểu trả về |
| 8. Phân biệt nơi lỗi | Tạo guard, tạo adapter, lookup, invocation, code test hay code nhánh |
| 9. Kiểm thử cả hai nhánh | Test trả `true` và `false` đều cho kết quả dự kiến |
| 10. Kiểm thử ngoại lệ | Test ném exception và từng nhánh ném exception được chuyển ra đúng |
| 11. Không nhầm short-circuit | Đối số Java được đánh giá trước khi gọi guard |
| 12. Đảm bảo phạm vi API | Dùng `java.lang.invoke` công khai trên JDK được hỗ trợ |

## 12. Câu hỏi tự đánh giá và bài thực hành

1. Với `target.type() = (int,String)String`, vì sao test `(int)boolean` hợp lệ nhưng test `(String)boolean` không hợp lệ?
2. Vì sao `test.type() = (int,String)Boolean` không thể đưa trực tiếp vào `guardWithTest`?
3. Target trả `String` còn fallback trả `Object`. Hai nhánh có được tự hợp nhất kiểu trả về không? Nếu cần, nên xử lý ở đâu?
4. Handle mới do `guardWithTest` trả về có kiểu giống `test` hay giống hai nhánh?
5. Khi test trả `false`, target có được thử chạy trước rồi fallback khi thất bại không? Giải thích.
6. `dropArguments(sourceTest, 0, int.class)` làm gì với test có type `(String)boolean`? Vì sao adapter đó giúp kiểm tra đối số thứ hai?
7. Dùng `dropArguments` như thế nào để một fallback `(int)String` khớp nhánh `(int,String)String`?
8. Nếu `guarded.type()` là `(int,String)String` nhưng lời gọi `invokeExact` cung cấp `long` ở đối số đầu, ngoại lệ thuộc bước tạo guard hay bước gọi?
9. Khi `guardWithTest` ném `IllegalArgumentException` ngay lúc tổ hợp, thông tin nào từ `MethodType` cần xem trước tiên?
10. Điều gì xảy ra nếu test ném exception trước khi trả `boolean`? Có nhánh nào được gọi không?
11. Nếu gọi `guarded.invokeExact(1, expensiveSource())` và test chỉ dùng `1`, `expensiveSource()` có được bỏ qua không? Vì sao?
12. Mở rộng ví dụ đầy đủ: thêm phương thức `fromApi(String)`, thích nghi test để kiểm tra tham số `source`, rồi thử gọi với `"API"` và `"CLI"`.
13. Thêm fallback chỉ nhận `int` và dùng `dropArguments` để tạo lại handle `(int,String)String`. In `type()` trước và sau khi chuyển đổi.
14. Thử tạo guard với test trả `int` và hai nhánh trả kiểu khác nhau. Ghi lại tại thời điểm nào xuất hiện lỗi, phân biệt với `WrongMethodTypeException` tại `invokeExact`.

**Ghi nhớ:** `MethodHandles.guardWithTest(test,target,fallback)` tạo một handle chọn nhánh dựa vào **test trả primitive `boolean`**. Hai nhánh phải có **`MethodType` giống hệt nhau**; danh sách tham số của test phải là **prefix** của danh sách tham số hai nhánh và có thể ngắn hơn. Nếu type không phù hợp, hãy thích nghi có chủ đích trước khi ghép. Lỗi cấu trúc khi tạo guard khác lỗi gọi sai chữ ký ở `invokeExact`, và guard **không tự bắt ngoại lệ** từ nhánh được chọn. Những hợp đồng này vẫn hữu ích trên JDK hiện đại.

## Tài liệu tham khảo chính thức

- [Java SE 25: `MethodHandles` — `guardWithTest`, `dropArguments` và các adapter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- [Java SE 25: `MethodHandle` — `type`, `invoke`, `invokeExact` và `asType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- [Java SE 25: `MethodType` — biểu diễn chữ ký handle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html).
- [Java SE 25: `WrongMethodTypeException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html).
- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).

