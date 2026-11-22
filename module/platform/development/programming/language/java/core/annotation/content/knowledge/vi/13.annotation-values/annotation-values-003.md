# Ngữ nghĩa `hashCode()` và cách so sánh phần tử mảng của annotation trong Java

## 1. Vì sao annotation cần quy tắc so sánh riêng?

Một annotation trong Java không chỉ là dòng chữ bắt đầu bằng `@`. Khi được giữ tới runtime, việc sử dụng annotation có thể được Reflection trả về dưới dạng một đối tượng triển khai `java.lang.annotation.Annotation`. Đối tượng này có `equals(Object)`, `hashCode()`, `toString()` và `annotationType()`.

Xét annotation type:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Endpoint {
    String path();
    int[] ports() default {80, 443};
}
~~~

Và hai class được đánh dấu:

~~~java
@Endpoint(path = "/status")
class StatusA {
}

@Endpoint(path = "/status", ports = {80, 443})
class StatusB {
}
~~~

Hai lần dùng có cách viết khác nhau: một nơi **bỏ qua** `ports` để nhận default, một nơi **ghi rõ** cùng giá trị. Về ngữ nghĩa annotation, chúng có **cùng annotation type và cùng giá trị hiệu lực của từng phần tử**. Vì vậy các đối tượng annotation mà runtime trả về phải `equals()` với nhau và có cùng `hashCode()`.

Ngược lại, `ports = {443, 80}` là giá trị mảng **khác** với `ports = {80, 443}`, vì thứ tự phần tử có ý nghĩa trong phép so sánh mảng.

Bài này làm rõ ba vấn đề:

1. Java định nghĩa thế nào là hai **annotation bằng nhau**.
2. Vì sao **mảng** trong annotation phải so sánh theo nội dung, không dùng `==` hoặc `Object.equals()`.
3. Java tính `hashCode()` của annotation như thế nào, đặc biệt với mảng, phần tử mặc định và annotation lồng nhau.

Các quy tắc này là **hợp đồng công khai của `java.lang.annotation.Annotation`**, không chỉ là thói quen của một phiên bản JDK cụ thể.

## 2. Hợp đồng `Annotation.equals(Object)`

Theo Java SE 17, hai đối tượng annotation `a` và `b` bằng nhau khi **cùng biểu diễn một annotation type** và **mọi cặp phần tử tương ứng đều có giá trị bằng nhau** theo quy tắc của kiểu phần tử đó.

Ví dụ:

~~~java
@interface Access {
    String role() default "reader";
    int[] levels() default {1, 2};
}
~~~

Nếu có:

~~~java
@Access
class One {
}

@Access(role = "reader", levels = {1, 2})
class Two {
}

@Access(role = "reader", levels = {2, 1})
class Three {
}
~~~

Thì về giá trị annotation:

- `One` và `Two` bằng nhau: `role` cùng bằng `"reader"`, `levels` cùng có hai phần tử `1, 2`.
- `One` và `Three` không bằng nhau: `levels` khác thứ tự.
- Việc annotation nằm trên hai **class khác nhau** không tự khiến giá trị annotation khác nhau. Chủ thể được gắn metadata không phải một phần trong `equals()` của annotation.
- Thứ tự **ghi các cặp tên = giá trị** của annotation tại nơi sử dụng không thay đổi phép so sánh; thứ tự **bên trong mảng** thì có.

### 2.1. Cách so sánh phụ thuộc kiểu của phần tử

| Kiểu phần tử annotation | Quy tắc `equals` của giá trị |
| --- | --- |
| Kiểu nguyên thủy trừ `float`, `double` | So sánh bằng `==` theo giá trị nguyên thủy |
| `float` | Dùng ngữ nghĩa `Float.valueOf(x).equals(Float.valueOf(y))` |
| `double` | Dùng ngữ nghĩa `Double.valueOf(x).equals(Double.valueOf(y))` |
| `String`, `Class`, enum | Dùng `x.equals(y)` |
| Annotation lồng nhau | Dùng `x.equals(y)` **đệ quy theo các phần tử annotation bên trong** |
| Mảng một chiều của kiểu hợp lệ | Dùng đúng overload `java.util.Arrays.equals(x, y)` |

Java cho phép các phần tử annotation có kiểu nguyên thủy, `String`, `Class`, enum, annotation khác, hoặc **mảng một chiều** của một kiểu được phép. Không khai báo `List<String>`, `Object` hay `int[][]` làm kiểu phần tử annotation.

### 2.2. Ngoại lệ đáng nhớ của `float` và `double`

Với phần tử `float` hoặc `double`, hợp đồng annotation sử dụng cách so sánh của wrapper tương ứng, **không đơn giản dùng toán tử `==`**:

- `NaN` được xem là bằng `NaN` theo `Float.equals`/`Double.equals`, khác với phép `NaN == NaN` trên giá trị floating-point nguyên thủy.
- `+0.0` và `-0.0` được xem là **khác nhau** theo wrapper equality, dù toán tử `+0.0 == -0.0` trả `true`.

Điều này bảo đảm quy tắc `equals()` của annotation nhất quán với `hashCode()` của những kiểu này. Trong các mảng `float[]` và `double[]`, `Arrays.equals` cũng có ngữ nghĩa tương ứng cho NaN và signed zero.

## 3. Vì sao `==` và `array.equals()` không so sánh nội dung mảng?

Trong Java, mảng là đối tượng. Hai mảng được tạo độc lập có thể chứa cùng các phần tử nhưng không cùng tham chiếu:

~~~java
int[] x = {80, 443};
int[] y = {80, 443};

System.out.println(x == y);             // false
System.out.println(x.equals(y));         // false
System.out.println(java.util.Arrays.equals(x, y)); // true
~~~

Đây là **fragment có thể đặt trong một phương thức**, không phải toàn bộ file Java. `x == y` so sánh danh tính tham chiếu; `int[].equals` kế thừa `Object.equals`, cũng không so sánh từng phần tử. `Arrays.equals(int[], int[])` mới kiểm tra độ dài và từng giá trị ở vị trí tương ứng.

Vì vậy, **annotation với phần tử mảng không thể so sánh theo `Object.equals` của mảng**. Hai annotation có `ports = {80, 443}` độc lập vẫn phải được xem là bằng nhau nếu các phần tử khác cũng trùng nhau.

Các overload cần biết:

~~~java
Arrays.equals(int[] a, int[] b)
Arrays.equals(boolean[] a, boolean[] b)
Arrays.equals(double[] a, double[] b)
Arrays.equals(Object[] a, Object[] b)
~~~

Các dạng nguyên thủy khác (`byte[]`, `short[]`, `char[]`, `long[]`, `float[]`) cũng có overload tương ứng. Mảng `String[]`, `Class<?>[]`, enum[] hoặc annotation[] sử dụng overload cho mảng tham chiếu, so sánh nội dung qua `equals` của mỗi phần tử.

**Thứ tự quan trọng:** `{80, 443}` không bằng `{443, 80}`. Ngay cả khi ứng dụng hiểu hai tập cổng như cùng một tập hợp, quy tắc Java cho annotation array vẫn so sánh theo **dãy có thứ tự**, không so sánh theo tập hợp.

**Không dùng `Arrays.deepEquals` để thay cho quy tắc chuẩn.** Annotation không cho khai báo phần tử là mảng lồng nhiều chiều. Với các loại mảng một chiều hợp lệ, `Arrays.equals` là hợp đồng chính thức. Nếu phần tử là mảng các annotation, mỗi annotation con tự áp dụng `equals` đệ quy; không cần tạo mảng hai chiều.

## 4. Công thức `hashCode()` của annotation

`Annotation.hashCode()` có **công thức được chỉ định trong API Java**, chứ không tùy ý lấy mã băm theo danh tính object.

Với mỗi phần tử annotation có tên `name` và giá trị hiệu lực `value`, đóng góp mã băm là:

```text
memberHash = (127 * name.hashCode()) ^ valueHash
```

Trong đó `^` là toán tử **bitwise XOR** trên số nguyên `int`, không phải phép lũy thừa.

Mã băm cuối cùng của annotation là **tổng đóng góp từ tất cả phần tử**, kể cả các phần tử được điền từ giá trị `default`:

```text
annotationHash =
    sum over all annotation elements:
        (127 * memberName.hashCode()) ^ memberValueHash
```

Việc nhân, XOR và cộng được thực hiện với số nguyên `int` 32 bit theo ngữ nghĩa Java (nếu tràn thì giữ 32 bit thấp). Không có ý nghĩa “mã băm dương duy nhất”; `hashCode()` có thể âm và có thể xảy ra va chạm.

### 4.1. `memberValueHash` được tính như thế nào?

| Loại giá trị của phần tử | Mã băm được sử dụng |
| --- | --- |
| Kiểu nguyên thủy `v` | `WrapperType.valueOf(v).hashCode()` |
| `String`, `Class`, enum | `v.hashCode()` |
| Annotation lồng nhau | `v.hashCode()`, tính đệ quy theo annotation con |
| Mảng nguyên thủy | `Arrays.hashCode(v)` theo đúng overload |
| Mảng tham chiếu hợp lệ | `Arrays.hashCode(v)` cho `Object[]` |

Hai quy tắc đặc biệt cần nhấn mạnh:

- Mặc định cũng được tính: nếu `int[] ports() default {80, 443};` không được truyền tại nơi sử dụng thì mã băm vẫn cộng đóng góp của `ports` với mảng `{80, 443}`.
- Phần tử mảng phải dùng **`Arrays.hashCode` theo nội dung**, không dùng `int[].hashCode()` hoặc `String[].hashCode()` từ `Object`.

Điều này tương ứng với quy tắc `Arrays.equals`: các mảng bằng nhau theo nội dung sẽ có cùng mã băm, nên annotation bằng nhau cũng có cùng mã băm.

### 4.2. Hai chiều của hợp đồng `equals/hashCode`

Đúng:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

**Không suy ra chiều ngược lại:**

```text
a.hashCode() == b.hashCode()  KHÔNG chứng minh a.equals(b)
```

Vì số lượng mã băm `int` hữu hạn trong khi số lượng annotation và giá trị có thể rất lớn, các đối tượng không bằng nhau vẫn có thể có mã băm trùng nhau. Mã băm phục vụ cấu trúc tra cứu như `HashMap`/`HashSet`, **không phải mã định danh duy nhất, checksum chống giả mạo hay hàm băm mật mã**.

## 5. Ví dụ Java 17 đầy đủ: so sánh mảng, default và tự tính hash

Tạo tệp duy nhất **`AnnotationHashDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RoutePolicy {
    String route();
    int[] ports() default {80, 443};
    String[] tags() default {"public", "stable"};
    double ratio() default 1.0;
}

@RoutePolicy(route = "/v1")
class FirstRoute {
}

@RoutePolicy(
        ratio = 1.0,
        tags = {"public", "stable"},
        ports = {80, 443},
        route = "/v1")
class SameRoute {
}

@RoutePolicy(route = "/v1", ports = {443, 80})
class ReorderedRoute {
}

public class AnnotationHashDemo {
    public static void main(String[] args) {
        RoutePolicy first =
                FirstRoute.class.getAnnotation(RoutePolicy.class);
        RoutePolicy same =
                SameRoute.class.getAnnotation(RoutePolicy.class);
        RoutePolicy reordered =
                ReorderedRoute.class.getAnnotation(RoutePolicy.class);

        System.out.println("First equals Same: "
                + first.equals(same));
        System.out.println("Same equals First: "
                + same.equals(first));
        System.out.println("First equals Reordered: "
                + first.equals(reordered));
        System.out.println("Equal hashes for equal annotations: "
                + (first.hashCode() == same.hashCode()));
        System.out.println("Matches specified hash formula: "
                + (first.hashCode() == calculateHash(first)));

        int[] x = {80, 443};
        int[] y = {80, 443};
        int[] reversed = {443, 80};

        System.out.println("Array reference equality: " + (x == y));
        System.out.println("Array content equality: "
                + Arrays.equals(x, y));
        System.out.println("Reversed array equality: "
                + Arrays.equals(x, reversed));
        System.out.println("Array content hash equality: "
                + (Arrays.hashCode(x) == Arrays.hashCode(y)));

        Set<RoutePolicy> unique = new HashSet<>();
        unique.add(first);
        unique.add(same);
        unique.add(reordered);
        System.out.println("Unique annotation values: "
                + unique.size());
    }

    private static int calculateHash(RoutePolicy policy) {
        return ((127 * "route".hashCode())
                       ^ policy.route().hashCode())
             + ((127 * "ports".hashCode())
                       ^ Arrays.hashCode(policy.ports()))
             + ((127 * "tags".hashCode())
                       ^ Arrays.hashCode(policy.tags()))
             + ((127 * "ratio".hashCode())
                       ^ Double.valueOf(policy.ratio()).hashCode());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 AnnotationHashDemo.java
java AnnotationHashDemo
~~~

**Stdout dự kiến, không phụ thuộc thứ tự duyệt reflection:**

~~~text
First equals Same: true
Same equals First: true
First equals Reordered: false
Equal hashes for equal annotations: true
Matches specified hash formula: true
Array reference equality: false
Array content equality: true
Reversed array equality: false
Array content hash equality: true
Unique annotation values: 2
~~~

### 5.1. Phân tích kết quả

**`FirstRoute` và `SameRoute` bằng nhau.** Trong `FirstRoute`, `ports`, `tags`, `ratio` nhận default; `SameRoute` ghi tường minh đúng các giá trị đó. Các giá trị hiệu lực như nhau, dù thứ tự ghi `ratio`, `tags`, `ports`, `route` ở source khác thứ tự khai báo trong annotation type.

**`ReorderedRoute` khác.** Mảng `ports = {443, 80}` khác theo thứ tự với `{80, 443}`, nên `equals()` trả `false`, mặc dù cùng hai số cổng.

**Phép kiểm tra công thức trả `true`.** `calculateHash` cộng chính xác đóng góp của bốn phần tử, sử dụng `Arrays.hashCode` cho hai mảng và `Double.valueOf(...).hashCode()` cho `ratio`. Thứ tự cộng không làm thay đổi kết quả `int`.

**Kích thước `HashSet` bằng `2`.** `first` và `same` là hai giá trị annotation tương đương, nên chỉ có một giá trị logic trong tập hợp; `reordered` không tương đương, nên còn thêm một giá trị nữa. Đây là lý do hợp đồng `equals/hashCode` đặc biệt quan trọng khi annotation được dùng làm key hoặc phần tử của cấu trúc dữ liệu dựa trên hash.

**Không in số mã băm cụ thể.** Chương trình kiểm tra tính đúng của công thức và tính bằng nhau của mã băm thay vì buộc người học ghi nhớ một số `int`. Với phần tử `Class`, enum hoặc các kiểu khác, giá trị hash cụ thể có thể phụ thuộc đối tượng/runtime; điều được Java bảo đảm là **hợp đồng so sánh và cách tính theo loại giá trị**, không phải hash dùng làm định danh bền vững giữa các lần chạy.

### 5.2. Vì sao có thể dùng `Arrays.hashCode` trong `calculateHash`?

Vì phần tử annotation `ports()` trả `int[]`, còn `tags()` trả `String[]`. Các overload `Arrays.hashCode(int[])` và `Arrays.hashCode(Object[])` lần lượt hash **nội dung của từng mảng**. Cách gọi:

~~~java
policy.ports().hashCode()
~~~

sẽ lấy hash của chính object mảng, không phù hợp với quy tắc hash phần tử mảng của annotation.

Trong phép tính thủ công, chú ý cặp ngoặc:

~~~java
(127 * "ports".hashCode()) ^ Arrays.hashCode(policy.ports())
~~~

Đóng góp được lấy bằng **XOR hai vế**, rồi **cộng** đóng góp của các phần tử. Dấu `^` không phải phép lũy thừa và không thay thế cho phép cộng toàn bộ phần tử.

## 6. Phần tử mảng của annotation có thể chứa những gì?

Java giới hạn phần tử annotation vào kiểu hợp lệ: nguyên thủy, `String`, `Class`, enum, annotation, hoặc **mảng một chiều** của một trong các loại trên. Vì vậy có các cách so sánh sau:

| Phần tử | Phép so sánh tương ứng | Phép băm tương ứng |
| --- | --- | --- |
| `int[] levels()` | `Arrays.equals(int[], int[])` | `Arrays.hashCode(int[])` |
| `boolean[] flags()` | `Arrays.equals(boolean[], boolean[])` | `Arrays.hashCode(boolean[])` |
| `double[] weights()` | `Arrays.equals(double[], double[])` | `Arrays.hashCode(double[])` |
| `String[] names()` | `Arrays.equals(Object[], Object[])` | `Arrays.hashCode(Object[])` |
| `Class<?>[] types()` | `Arrays.equals(Object[], Object[])` | `Arrays.hashCode(Object[])` |
| `Mode[] modes()` | `Arrays.equals(Object[], Object[])` | `Arrays.hashCode(Object[])` |
| `Nested[] nested()` | `Arrays.equals(Object[], Object[])`, gọi `equals` của từng annotation con | `Arrays.hashCode(Object[])`, gọi `hashCode` của annotation con |

Ở hai dòng cuối, `Mode` là một enum minh họa và `Nested` là một annotation type minh họa. Hãy nhớ rằng `String[]`, enum[] và annotation[] đều là **mảng tham chiếu**; Java không có overload `Arrays.hashCode(String[])` riêng mà sử dụng phiên bản `Object[]`.

### Annotation lồng nhau được so sánh đệ quy

Ví dụ fragment định nghĩa:

~~~java
@interface Nested {
    String code() default "ok";
}

@interface Outer {
    Nested nested() default @Nested;
    Nested[] checks() default {@Nested(code = "a"), @Nested(code = "b")};
}
~~~

Đây là hai annotation types, không phải một chương trình có `main` độc lập.

Nếu hai đối tượng `Outer` có các `Nested` với `code()` giống nhau, phép so sánh `Outer.equals(...)` sẽ dựa vào `Nested.equals(...)`. Phần tử `checks` là một mảng annotation, nên Java dùng `Arrays.equals` theo thứ tự và gọi `equals` của từng annotation ở vị trí tương ứng. Tương tự, `hashCode` của `Outer` sử dụng mã băm đệ quy của annotation con.

Không cần `Arrays.deepEquals` để hỗ trợ `Nested[]`: annotation con có `equals` theo nội dung riêng, còn `Nested[][]` **không phải kiểu phần tử annotation hợp lệ**.

## 7. Giá trị mặc định có ảnh hưởng trực tiếp đến `equals/hashCode`

Một điểm dễ bỏ sót: **mọi phần tử đều được xét**, dù người lập trình không ghi chúng ở nơi sử dụng.

~~~java
@interface Policy {
    String name() default "standard";
    int[] levels() default {1, 2};
}
~~~

Hai lần sử dụng:

~~~java
@Policy
class A {
}

@Policy(name = "standard", levels = {1, 2})
class B {
}
~~~

Có cùng giá trị hiệu lực. Khi runtime đọc chúng, `Policy.name()` ở cả hai là `"standard"`, `Policy.levels()` ở cả hai là `{1, 2}`. Vì vậy `equals()` bằng nhau và `hashCode()` tính cả đóng góp của `name` và `levels`.

**Không phải** vì source `@Policy` không ghi `levels` nên công thức `hashCode()` bỏ qua phần tử đó. Hash của annotation phải nhất quán với giá trị thực tế mà annotation biểu diễn.

### Nếu thư viện đổi giá trị default thì sao?

Giả sử phiên bản cũ định nghĩa `int[] levels() default {1, 2};`, sau đó bản mới đổi thành `default {1, 3};`. Những annotation nơi sử dụng **không ghi `levels`** có thể nhận giá trị hiệu lực khác khi mã được chạy/giải mã với định nghĩa annotation mới.

Do `equals()` và `hashCode()` phụ thuộc vào giá trị phần tử, việc đổi default có thể làm **thay đổi hành vi so sánh và tra cứu trong hash collection**, dù source client không đổi. Không nên coi thay đổi default chỉ là sửa tài liệu hoặc thay đổi thẩm mỹ API.

Ngược lại, nếu một nơi sử dụng đã **ghi tường minh** `levels = {1, 2}`, việc đổi giá trị mặc định của annotation type không tự sửa giá trị đã ghi rõ ở nơi đó.

## 8. Những trường hợp đặc biệt của `float`, `double` và mảng

Quy tắc `equals/hashCode` phải thống nhất ngay cả với các giá trị floating-point đặc biệt.

~~~java
double positiveZero = 0.0d;
double negativeZero = -0.0d;

System.out.println(positiveZero == negativeZero);
System.out.println(Double.valueOf(positiveZero)
                         .equals(Double.valueOf(negativeZero)));
~~~

**Kết quả:**

~~~text
true
false
~~~

Đây là fragment chạy được trong method. Với phần tử annotation kiểu `double`, hợp đồng equality sử dụng wrapper `Double.equals`, nên `+0.0d` và `-0.0d` **không** được xem là bằng nhau. Một mảng `double[]` cũng dùng `Arrays.equals(double[], double[])`, vốn phân biệt hai trường hợp trên.

Với `NaN`, `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` trả `true`, còn phép `Double.NaN == Double.NaN` trả `false`. Quy tắc này giúp `equals()` của annotation giữ tính phản xạ và nhất quán với hash của `Double`.

**Đừng tự viết** bộ so sánh chung chỉ dùng `==` trên các phần tử số; cách làm ấy sai với `float`/`double` ở những trường hợp đặc biệt. Tốt nhất dùng trực tiếp `annotation.equals(other)`, trừ khi đang thực sự xây dựng công cụ cần mô phỏng chính xác hợp đồng Java.

## 9. Vì sao không nên dùng `==` cho annotation object?

Phép `==` trên hai đối tượng annotation kiểm tra **chúng có cùng tham chiếu object hay không**. Nó không kiểm tra chúng biểu diễn cùng metadata.

~~~java
RoutePolicy a = FirstRoute.class.getAnnotation(RoutePolicy.class);
RoutePolicy b = SameRoute.class.getAnnotation(RoutePolicy.class);

System.out.println(a.equals(b)); // true
~~~

Fragment trên sử dụng các lớp đã khai báo trong ví dụ đầy đủ ở phần 5. Hai class khác nhau nhưng hai giá trị annotation tương đương. Đừng thay `a.equals(b)` bằng `a == b` để kết luận về **nghĩa** của annotation.

Các runtime/JDK có thể sử dụng đối tượng proxy hoặc implementation-specific object để biểu diễn annotation. Vì vậy `getClass()` của đối tượng annotation không phải cách đáng tin để biết annotation type; phương thức đúng là `annotation.annotationType()`.

Cũng không nên dựa vào `System.identityHashCode(annotation)` để so sánh giá trị annotation. Nó phục vụ danh tính đối tượng, khác với `Annotation.hashCode()` được định nghĩa theo các phần tử.

## 10. Có thể sửa mảng nhận được từ annotation để thay đổi `equals/hashCode` không?

Không. Annotation là metadata được quy định ở thời điểm biên dịch/ghi vào class file hoặc do công cụ tạo ra theo hợp đồng tương ứng; **việc thay đổi một mảng Java mà phương thức phần tử trả về không phải cơ chế cập nhật annotation đã gắn trong mã nguồn**.

Ví dụ minh họa ý tưởng cần tránh:

~~~java
RoutePolicy policy =
        FirstRoute.class.getAnnotation(RoutePolicy.class);

int[] copy = policy.ports();
copy[0] = 999; // KHÔNG có nghĩa đã sửa metadata của FirstRoute
~~~

Fragment này cần các định nghĩa ở phần 5. Các implementation runtime thông thường bảo vệ giá trị mảng của annotation khỏi sửa đổi bên ngoài (chẳng hạn trả bản sao), và logic ứng dụng **không được dựa** vào khả năng mutate dữ liệu nội bộ của đối tượng annotation.

Nếu cần tạo một cấu hình mutable, hãy chuyển dữ liệu annotation sang một DTO/config object **độc lập**. Khi dùng mảng làm key trong cấu trúc dữ liệu, cũng phải chú ý: mảng Java tự nó không có `equals/hashCode` theo nội dung, nên không thể dùng trực tiếp `int[]` như một key nội dung trong `HashMap` mà mong các mảng độc lập cùng phần tử là bằng nhau. Có thể dùng immutable wrapper phù hợp hoặc canonical representation khi thiết kế key.

## 11. Sử dụng annotation trong `HashMap` và `HashSet`

Với hợp đồng `equals/hashCode`, annotation object có thể dùng làm key trong `HashMap` hoặc phần tử trong `HashSet`:

~~~java
Set<RoutePolicy> unique = new HashSet<>();
unique.add(first);
unique.add(same);
unique.add(reordered);
~~~

Trong ví dụ đầy đủ phần 5, `first` và `same` có metadata tương đương nên chỉ chiếm **một** mục logic; `reordered` là giá trị khác nên tập có hai mục.

Tuy nhiên, cần cân nhắc ngữ nghĩa nghiệp vụ:

- Nếu muốn phân biệt **nguồn gốc class được đánh dấu**, annotation object **không đủ** làm key: cùng annotation có thể xuất hiện trên nhiều class.
- Nếu muốn phân biệt cấu hình annotation theo **giá trị**, dùng annotation object với `equals/hashCode` là phù hợp.
- Nếu muốn so sánh các phần tử mảng như **tập không có thứ tự**, hợp đồng annotation tiêu chuẩn không đáp ứng nhu cầu đó. Cần chuyển sang một key riêng có quy tắc canonical hóa/sắp xếp, **không thay đổi ngữ nghĩa Java của `Annotation.equals`**.
- Không lưu kết quả `hashCode` như định danh lâu dài trong database, file hay giao thức mạng. Hash là công cụ tra cứu, không phải định danh bất biến toàn cục.

## 12. Các lỗi thường gặp

**Lỗi 1 — dùng `==` để so sánh hai annotation object.** `==` kiểm tra danh tính object, không kiểm tra metadata. Dùng `equals()`.

**Lỗi 2 — dùng `int[].equals(...)` hoặc `String[].equals(...)` để so sánh phần tử mảng.** Các mảng không override `Object.equals`; dùng `Arrays.equals` theo đúng overload.

**Lỗi 3 — dùng `array.hashCode()` trong công thức hash của annotation.** Sai với phần tử mảng. Phải dùng `Arrays.hashCode` theo nội dung.

**Lỗi 4 — bỏ qua phần tử có default khi tính mã băm.** Sai. Giá trị default là một phần của giá trị hiệu lực và đóng góp vào hash như mọi phần tử khác.

**Lỗi 5 — cho rằng mảng cùng phần tử nhưng khác thứ tự là bằng nhau.** Sai. `Arrays.equals` so sánh theo từng vị trí.

**Lỗi 6 — cho rằng `a.hashCode() == b.hashCode()` chứng tỏ `a.equals(b)`.** Sai. Có thể có hash collision.

**Lỗi 7 — cho rằng `+0.0` và `-0.0` là bằng nhau trong phần tử `float/double` vì `==` trả `true`.** Sai. Annotation equality dùng wrapper equality.

**Lỗi 8 — dùng `Arrays.deepEquals` vì thấy mảng chứa annotation.** Không cần; phần tử annotation chỉ được là mảng một chiều, và annotation con đã có `equals` theo nội dung.

**Lỗi 9 — in `annotation.toString()` rồi so sánh chuỗi để kết luận hai annotation bằng nhau.** Không nên. `toString` có hình thức trình bày phụ thuộc implementation; `equals` là hợp đồng chính thức.

**Lỗi 10 — tự triển khai `Annotation` và chỉ viết `equals/hashCode` theo `Object` hoặc chỉ dùng vài phần tử.** Nếu tự xây dựng implementation, phải tuân thủ đầy đủ hợp đồng của interface `Annotation`, bao gồm mọi phần tử, mảng, defaults và trường hợp floating-point; bỏ sót sẽ làm hỏng `HashSet`/`HashMap`.

## 13. Bài tập tự kiểm tra

**Bài 1.** Hai lần sử dụng:

~~~java
@Endpoint(path = "/a")
class A1 {
}

@Endpoint(path = "/a", ports = {80, 443})
class A2 {
}
~~~

Giả sử `Endpoint.ports()` có `default {80, 443}`. Hai đối tượng `Endpoint` đọc từ hai class có bằng nhau không?  
**Đáp án:** Có. `ports` nhận cùng giá trị hiệu lực, kể cả khi một nơi dùng default.

**Bài 2.** Nếu đổi `ports` của class thứ hai thành `{443, 80}`, `equals()` ra sao?  
**Đáp án:** `false`, vì mảng khác thứ tự. Không cần khẳng định chắc chắn hai mã băm khác nhau: hai giá trị không bằng nhau vẫn có thể trùng hash.

**Bài 3.** Công thức cho đóng góp của phần tử `int[] ports()` là gì?  
**Đáp án:** `(127 * "ports".hashCode()) ^ Arrays.hashCode(portsValue)`. Sau đó cộng đóng góp này với các phần tử còn lại.

**Bài 4.** `new int[]{1, 2}.equals(new int[]{1, 2})` có trả `true` không?  
**Đáp án:** Không. Hai mảng là hai object khác nhau, `Object.equals` của mảng không so sánh nội dung. `Arrays.equals(new int[]{1, 2}, new int[]{1, 2})` mới trả `true`.

**Bài 5.** Một annotation có phần tử `Nested[] checks()`. Có cần dùng `Arrays.deepEquals` không?  
**Đáp án:** Không. Dùng `Arrays.equals(Nested[], Nested[])`, lần lượt gọi `equals()` của từng `Nested`; phép so sánh annotation con được thực hiện đệ quy theo phần tử.

**Bài 6.** Vì sao `+0.0d` và `-0.0d` là hai giá trị khác nhau theo `Annotation.equals` khi chúng nằm ở phần tử `double`?  
**Đáp án:** Hợp đồng dùng `Double.valueOf(x).equals(Double.valueOf(y))`, phân biệt signed zero; không dùng `==` nguyên thủy.

**Bài 7.** Nếu `A.equals(B)` đúng thì chắc chắn `A.hashCode() == B.hashCode()` đúng không? Còn chiều ngược lại?  
**Đáp án:** Chiều đầu chắc chắn đúng; chiều ngược không đúng vì hash collision.

**Bài thực hành:** Chạy `AnnotationHashDemo.java`. Sau đó đổi `SameRoute` thành `@RoutePolicy(route = "/v1", tags = {"stable", "public"})` và chạy lại. Dự đoán `First equals Same`, `Equal hashes for equal annotations`, `Unique annotation values`. Cuối cùng hoàn nguyên `SameRoute` và thử thay phần tử `ratio` của một nơi bằng `-0.0` rồi kiểm tra sự khác biệt so với `ratio = 0.0`. Dùng `equals` để xác nhận ngữ nghĩa, không đoán dựa trên hash.

## 14. Tham khảo chính thức

- [Java SE 17 — `java.lang.annotation.Annotation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html): hợp đồng đầy đủ của `equals` và công thức `hashCode`.
- [Java SE 17 — `java.util.Arrays`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): các overload `equals`, `hashCode` của mảng nguyên thủy và mảng tham chiếu.
- [JLS Java SE 17 §9.6 — Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6): cấu trúc annotation type, các kiểu phần tử hợp lệ và default.
- [Java SE 17 — `java.lang.Object`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): quy tắc tổng quát về `equals` và `hashCode` trên object.

Tóm lại, hãy coi mỗi annotation như **một giá trị cấu trúc**: cùng annotation type và **mọi phần tử có cùng giá trị** thì bằng nhau. Với mảng, **`Arrays.equals` và `Arrays.hashCode`** là cặp quy tắc then chốt; công thức hash tổng thể cộng đóng góp **`(127 * tên.hashCode()) ^ giáTrịHash`** của **mọi phần tử, kể cả default**.