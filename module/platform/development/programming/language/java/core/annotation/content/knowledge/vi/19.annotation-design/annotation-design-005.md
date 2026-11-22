# Xác định quy tắc xung đột, độ ưu tiên và trường hợp thiếu annotation trong Java

Khi thiết kế annotation, viết một `@interface` chỉ là bước đầu. Phần dễ phát sinh lỗi nằm ở **hợp đồng xử lý metadata**: nếu một class và method đều có annotation thì giá trị nào được dùng? Nếu cùng vị trí có hai annotation mâu thuẫn thì phải làm gì? Nếu không có annotation nào thì nên dùng mặc định, tìm kế thừa hay báo lỗi?

Java chỉ định nghĩa cú pháp, những vị trí được gắn annotation, vòng đời lưu giữ, và cách các API lấy annotation. **Java không tự biết quy tắc nghiệp vụ rằng annotation nào “quan trọng hơn” annotation nào.** Thứ tự ưu tiên, cơ chế xung đột và hành vi khi metadata vắng mặt phải được bạn **viết thành một chính sách rõ ràng, nhất quán và kiểm thử được** trong library, framework hoặc annotation processor.

Bài học dùng tình huống minh họa về quyền truy cập để giải thích. Ví dụ này nhằm dạy **thiết kế annotation**, không phải thư viện bảo mật hoàn chỉnh: chỉ có mã kiểm tra quyền thực sự được gọi tại điểm thực thi mới giúp thực thi chính sách truy cập.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Định nghĩa *conflict*, *override*, *fallback*, *missing* và *invalid value* trong ngữ cảnh annotation.
- Quyết định chính sách ưu tiên như `method > class > default` và giải thích trường hợp hai annotation ở **cùng cấp** khác với annotation ở **khác cấp**.
- Phân biệt “không khai báo annotation” với “khai báo annotation mang giá trị mặc định” và “cấu hình rõ ràng để tắt hoặc cho phép”.
- Dùng `getDeclaredAnnotation(...)` hoặc `getAnnotation(...)` có chủ đích, không dựa vào suy đoán về `@Inherited`, method override hay interface.
- Xử lý metadata thiếu bằng **default an toàn**, **báo lỗi sớm** hoặc **fallback rõ ràng**, tùy hợp đồng ứng dụng.
- Viết một resolver không phụ thuộc vào thứ tự trả về của `getAnnotations()`.
- Phát hiện xung đột trước khi quyết định độ ưu tiên; không vô tình che khuất cấu hình sai.
- Tạo bài kiểm thử theo ma trận method/class/không có/conflict/invalid.
- Hiểu khi nào nên chuyển lỗi từ runtime sang compile-time bằng annotation processor.

## 2. Vì sao annotation cần một “hợp đồng xung đột”?

Giả sử tự thiết kế hai annotation:

~~~java
@PermitAll
@Roles({"admin"})
public void deleteEverything() {}
~~~

`@PermitAll` nghĩa là “mở”, còn `@Roles({"admin"})` nghĩa là “chỉ người có role admin”. Chúng xuất hiện **trên cùng một method**, cùng mô tả một quyết định. Nếu mã kiểm tra `@PermitAll` trước thì có thể cho phép mọi người; nếu mã kiểm tra `@Roles` trước thì chặn những người không có role. Không được để ý nghĩa phụ thuộc vào thứ tự duyệt một mảng annotation hoặc cấu trúc `if` viết tùy hứng.

Mặt khác:

~~~java
@Roles({"staff"})
class Reports {
    @PermitAll
    public void ping() {}
}
~~~

Ở đây hai annotation nằm **khác cấp**: class và method. Có thể đặt luật rằng method cụ thể hơn, nên `ping()` công khai dù mặc định của class là role `staff`. Đó là **override có chủ ý**, không nhất thiết là xung đột.

Cuối cùng:

~~~java
class Unmarked {
    public void probe() {}
}
~~~

Không có annotation ở cả class lẫn method. Hệ thống phải biết chọn **deny**, **allow**, giá trị cấu hình bên ngoài hay **lỗi thiếu cấu hình**. Không thể hiểu “không thấy gì” thành một lựa chọn bảo mật tùy tiện.

Hãy phân loại trước khi viết code:

| Tình huống | Tên vấn đề | Câu hỏi thiết kế |
| --- | --- | --- |
| Cùng method có `@PermitAll` và `@Roles` | Xung đột cùng cấp | Báo lỗi hay có quy tắc ưu tiên giữa hai annotation type? |
| Class có `@Roles`, method có `@PermitAll` | Override khác cấp | Method được phép ghi đè class không? |
| Method không có, class có | Fallback | Dùng cấu hình class không? |
| Method và class đều không có | Missing | Mặc định an toàn hay cấu hình bắt buộc? |
| `@Roles({})` | Invalid value | Danh sách rỗng có nghĩa gì? Báo lỗi hay coi như deny? |
| Class cha/interface có annotation | Kế thừa/tìm kiếm | Có dò superclass, interface, overridden method không? |
| Cùng type annotation xuất hiện nhiều lần | Repeatable/aggregate | Ghép theo union, intersection, ưu tiên hay từ chối? |

Một thư viện tốt viết được câu trả lời cho các dòng này **trước khi có traffic thực tế**.

## 3. Phân biệt các khái niệm nền tảng

### 3.1. Annotation type khác giá trị annotation

`@Roles({"staff"})` và `@Roles({"admin"})` là **cùng annotation type** `Roles` nhưng có element values khác nhau. Annotation type có thể khai báo giá trị mặc định:

~~~java
@interface Priority {
    int value() default 10;
}
~~~

Nếu source ghi `@Priority`, giá trị hiệu lực của `value()` là `10`. Điều đó **khác** với không có `@Priority`. Khi không có, `getAnnotation(Priority.class)` trả `null`; khi có `@Priority`, API trả annotation instance và `value()` trả `10`.

Sự phân biệt cực kỳ quan trọng khi người dùng muốn nói “cố ý dùng mặc định” hoặc “để cho lớp chứa quyết định”.

### 3.2. “Thiếu” và “không hợp lệ” không giống nhau

- **Thiếu:** cả method và class không khai báo policy.
- **Không hợp lệ:** người viết có gắn `@Roles({})` nhưng thư viện yêu cầu ít nhất một role.
- **Xung đột:** cùng vị trí đồng thời có `@PermitAll` và `@Roles(...)`.

Không nên xử lý tất cả trường hợp bằng cùng một `null -> default allow`. Một annotation **đã khai báo nhưng sai** cần được phát hiện và báo lỗi, thay vì âm thầm bỏ qua rồi fallback.

### 3.3. Độ ưu tiên không giống vòng đời retention

`@Retention(RUNTIME)` khiến annotation có thể được Reflection đọc lúc chạy; `@Retention(SOURCE)` phù hợp với annotation processor ở lúc biên dịch. **Retention không quyết định annotation nào thắng**.

`@Target({TYPE, METHOD})` cho phép gắn annotation lên khai báo class và method; nó cũng **không quyết định việc method có ưu tiên class**. Đây là chính sách của bộ xử lý.

`@Inherited` ảnh hưởng cách Java tìm một số annotation trên **class**, nhưng không sinh ra một bộ giải quyết xung đột theo nghiệp vụ. Bài sẽ đặt quy tắc tra cứu rõ ràng để không nhầm với inheritance.

## 4. Chọn một chính sách có thể diễn đạt thành bảng

Trong ví dụ, ta chọn hợp đồng:

1. **Cấp method có ưu tiên** hơn cấp class trong việc xác định quyết định áp dụng cho method.
2. **Mỗi cấp chỉ được chứa tối đa một lựa chọn** trong tập `@PermitAll` và `@Roles`. Cùng cấp có cả hai là **lỗi cấu hình**, không âm thầm chọn một.
3. **Giá trị `@Roles` phải hợp lệ**: mảng role không rỗng; mỗi role gồm chữ cái thường tiếng Anh (`[a-z]+`) để đơn giản hóa demo.
4. Trước khi áp dụng override, **validate cả cấu hình class lẫn method**. Một cấu hình sai ở class phải được báo, dù method nào đó có annotation riêng.
5. Nếu method không khai báo policy thì **fallback tới class**.
6. Nếu cả hai cấp đều thiếu: mặc định `DENY` với chế độ thông thường; nếu người gọi yêu cầu policy bắt buộc (`required=true`), trả lỗi `MISSING`.
7. Trong demo **chỉ xét annotation khai báo trực tiếp** tại class và method, không tự quét superclass, interface hay method override. Nếu cần thừa kế phức tạp, đó phải là một phần riêng của hợp đồng và cần thêm test.

Bảng quyết định:

| Method | Class | Kết quả (nếu đều hợp lệ) |
| --- | --- | --- |
| `@PermitAll` | Bất kỳ policy hợp lệ nào hoặc thiếu | `ALLOW@method` |
| `@Roles({"admin"})` | Policy hợp lệ hoặc thiếu | `ROLES[admin]@method` |
| Không có | `@PermitAll` | `ALLOW@class` |
| Không có | `@Roles({"staff"})` | `ROLES[staff]@class` |
| Không có | Không có, `required=false` | `DENY@default` |
| Không có | Không có, `required=true` | `MISSING` (lỗi) |
| Hai annotation mâu thuẫn cùng cấp | Bất kỳ | `CONFLICT` (lỗi) |
| `@Roles({})` tại một cấp | Bất kỳ | `INVALID_ROLES` (lỗi) |

Bảng này biểu diễn **chính sách ứng dụng giả định**, không phải một luật tự động của JVM. Nếu áp dụng cho lĩnh vực khác, ví dụ JSON mapping, test runner hoặc dependency injection, có thể chọn chính sách khác nhưng vẫn phải minh bạch và nhất quán.

## 5. Ví dụ Java 17+ chạy độc lập

Tạo một file duy nhất tên **`AccessPolicyDemo.java`** (không có `package`). File dưới đây chứa hai annotation type, các class ví dụ, `Decision` record, `PolicyResolver` và một class public có `main`.

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface PermitAll {}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Roles {
    String[] value();
}

@Roles({"staff"})
class Reports {
    public void list() {}
    @PermitAll public void ping() {}
}

@PermitAll
class Portal {
    @Roles({"admin"}) public void delete() {}
    public void home() {}
}

class Unmarked {
    public void probe() {}
    public void strict() {}
}

class Conflicted {
    @PermitAll @Roles({"ops"}) public void broken() {}
}

class InvalidRoles {
    @Roles({}) public void empty() {}
}

@PermitAll @Roles({"ops"})
class InvalidClass {
    @PermitAll public void action() {}
}

record Decision(String rule, String source) {
    @Override public String toString() {
        return rule + "@" + source;
    }
}

class PolicyResolver {
    static Decision read(AnnotatedElement element, String where) {
        PermitAll permitAll = element.getDeclaredAnnotation(PermitAll.class);
        Roles roles = element.getDeclaredAnnotation(Roles.class);

        if (permitAll != null && roles != null) {
            throw new IllegalStateException("CONFLICT@" + where);
        }
        if (roles != null) {
            String[] names = roles.value();
            if (names.length == 0
                    || Arrays.stream(names).anyMatch(
                        name -> name == null
                                || !name.matches("[a-z]+"))) {
                throw new IllegalStateException("INVALID_ROLES@" + where);
            }
            return new Decision("ROLES[" + String.join(",", names) + "]",
                    where);
        }
        return permitAll != null ? new Decision("ALLOW", where) : null;
    }

    static Decision resolve(Class<?> owner, String methodName, boolean required)
            throws NoSuchMethodException {
        Method method = owner.getDeclaredMethod(methodName);
        // Validate class and method independently, even when method overrides.
        Decision classRule = read(owner, "class");
        Decision methodRule = read(method, "method");
        if (methodRule != null) return methodRule;
        if (classRule != null) return classRule;
        if (required) throw new IllegalStateException("MISSING@method+class");
        return new Decision("DENY", "default");
    }
}

public class AccessPolicyDemo {
    static void show(Class<?> owner, String method, boolean required)
            throws NoSuchMethodException {
        try {
            System.out.println(owner.getSimpleName() + "." + method + "="
                    + PolicyResolver.resolve(owner, method, required));
        } catch (IllegalStateException e) {
            System.out.println(owner.getSimpleName() + "." + method
                    + "=ERROR:" + e.getMessage());
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        show(Reports.class, "list", false);
        show(Reports.class, "ping", false);
        show(Portal.class, "delete", false);
        show(Portal.class, "home", false);
        show(Unmarked.class, "probe", false);
        show(Unmarked.class, "strict", true);
        show(Conflicted.class, "broken", false);
        show(InvalidRoles.class, "empty", false);
        show(InvalidClass.class, "action", false);
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 AccessPolicyDemo.java
java AccessPolicyDemo
~~~

**Stdout chính xác:**

~~~text
Reports.list=ROLES[staff]@class
Reports.ping=ALLOW@method
Portal.delete=ROLES[admin]@method
Portal.home=ALLOW@class
Unmarked.probe=DENY@default
Unmarked.strict=ERROR:MISSING@method+class
Conflicted.broken=ERROR:CONFLICT@method
InvalidRoles.empty=ERROR:INVALID_ROLES@method
InvalidClass.action=ERROR:CONFLICT@class
~~~

Kết quả này đã được biên dịch bằng `javac --release 17` và chạy thành công với JDK có hỗ trợ Java 17.

### Phân tích lần lượt

1. **`Reports.list`:** method không gắn policy, class có `@Roles({"staff"})`, nên lấy policy từ class.
2. **`Reports.ping`:** method có `@PermitAll`, class có `@Roles`. Hai annotation **khác cấp**, chính sách ưu tiên method nên `ALLOW@method`.
3. **`Portal.delete`:** class có `@PermitAll` nhưng method cụ thể có `@Roles({"admin"})`. Method được quyền hạn chế hơn, kết quả `ROLES[admin]@method`.
4. **`Portal.home`:** method không có policy; dùng `@PermitAll` trên class.
5. **`Unmarked.probe`:** không có policy ở cả hai cấp và `required=false`; **mặc định DENY**.
6. **`Unmarked.strict`:** không có policy nhưng `required=true`; trả lỗi `MISSING`, không chọn mặc định một cách im lặng.
7. **`Conflicted.broken`:** trên **cùng method** có `@PermitAll` và `@Roles({"ops"})`; báo `CONFLICT@method`.
8. **`InvalidRoles.empty`:** có `@Roles({})` nhưng danh sách role rỗng; báo `INVALID_ROLES@method`. Không được coi role rỗng là “không khai báo”.
9. **`InvalidClass.action`:** class có hai annotation mâu thuẫn; dù method có `@PermitAll`, resolver vẫn **validate class trước** rồi báo `CONFLICT@class`. Điều này tránh để annotation method che một cấu hình class lỗi mà không ai biết.

### Vì sao dùng `record Decision`?

Java 17 hỗ trợ records. `Decision` trong demo chỉ mang hai trường: `rule` (quyết định) và `source` (nơi lấy), cho phép output kèm **nguồn quyết định** như `ALLOW@method`. Khi debug hoặc viết test, thông tin nguồn rất hữu ích: hai policy có hành vi giống nhau nhưng một policy được khai báo trực tiếp, policy kia đến từ fallback.

Trong ứng dụng lớn, nên dùng enum/kiểu dữ liệu chặt chẽ, ví dụ `AccessMode { DENY, ALLOW, ROLES }` cộng danh sách roles immutable, thay vì ghép rule vào chuỗi. Demo dùng `String` để ưu tiên cách đọc và stdout đơn giản.

## 6. Hiểu sâu thuật toán resolver

Bốn bước của `PolicyResolver.resolve(...)`:

~~~text
1. Đọc & validate policy khai báo trên class
                 |
2. Đọc & validate policy khai báo trên method
                 |
3. Nếu method có policy -> dùng method
   Nếu không, class có policy -> dùng class
                 |
4. Nếu cả hai thiếu:
   required=true  -> báo MISSING
   required=false -> trả DENY@default
~~~

**Không được đảo thứ tự “validate” và “chọn độ ưu tiên” một cách tùy ý.** Nếu code chọn method ngay khi thấy `@PermitAll` rồi bỏ qua hoàn toàn class, một class có xung đột nội tại sẽ không bị phát hiện. Chính sách của bài yêu cầu **tất cả cấu hình xuất hiện ở hai cấp phải hợp lệ**.

Tuy nhiên, có hệ thống chủ đích chỉ validate policy hiệu lực hoặc có quy tắc loại bỏ một phần cấu hình cha. Khi đó cần diễn đạt rõ mức validate khác nhau và kiểm thử trường hợp bị override. Quan trọng không phải mọi framework phải dùng thứ tự giống bài, mà là **thứ tự phải được định nghĩa trước**.

### 6.1. Hàm `read` thực hiện nhiệm vụ gì?

`read(AnnotatedElement element, String where)`:

- Đọc trực tiếp hai annotation types.
- Nếu cùng xuất hiện trên một `AnnotatedElement`, trả lỗi xung đột.
- Nếu thấy `@Roles`, kiểm tra số lượng và định dạng role names.
- Nếu thấy `@PermitAll`, tạo quyết định ALLOW.
- Nếu không thấy loại nào, trả `null` để resolver biết rằng **cấp này thiếu policy**.

Việc trả `null` ở đây là một **ký hiệu nội bộ cho “không khai báo”**, chứ không phải một policy như `DENY`. Nhờ vậy resolver có thể phân biệt fallback với deny tường minh.

Trong code sản phẩm, có thể thay `null` bằng `Optional<Decision>` hoặc một sealed hierarchy mô tả `Missing`/`Configured`/`Invalid`. Nhưng không nhất thiết nên bọc mọi đoạn code bằng kiểu phức tạp khi ví dụ nhỏ đã rõ.

### 6.2. Không dùng thứ tự của `getAnnotations()` làm thứ tự ưu tiên

Cách thiết kế không tốt:

~~~java
// KHÔNG dùng vị trí trong mảng làm thứ tự ưu tiên nghiệp vụ.
Annotation[] annotations = method.getAnnotations();
if (annotations.length > 0) {
    Annotation winner = annotations[0];
}
~~~

Java Reflection cung cấp annotations để đọc metadata, không hứa “annotation viết trước trong source luôn thắng”. Nếu cần phân giải, đọc **đúng type** được nhận biết và thực hiện các quy tắc rõ ràng. Nếu phải gắn thứ tự, hãy thiết kế element `priority` có nghĩa cụ thể, chỉ rõ tie-break và kiểm thử.

Hơn nữa, `@Target` không cấm hai annotation types khác nhau xuất hiện cùng vị trí. Nếu chúng loại trừ nhau theo nghiệp vụ, phải tự validate (hoặc dùng annotation processor để phát hiện sớm).

## 7. Phân biệt class, method, superclass và interface

Trong demo, resolver dùng:

~~~java
element.getDeclaredAnnotation(PermitAll.class);
element.getDeclaredAnnotation(Roles.class);
~~~

`AnnotatedElement.getDeclaredAnnotation(...)` chỉ đọc annotation được **khai báo trực tiếp** trên phần tử đang xét. Vì vậy thuật toán của bài **không** tìm policy từ superclass, interface hay overridden method.

Đây là một lựa chọn quan trọng, không phải giới hạn bắt buộc. Nếu framework muốn hỗ trợ kế thừa, phải viết thành hợp đồng riêng:

| Nơi có policy | Mặc định trong demo | Nếu muốn hỗ trợ |
| --- | --- | --- |
| Method khai báo trực tiếp | Đọc | Giữ làm ưu tiên cao nhất |
| Class khai báo trực tiếp | Đọc | Giữ sau method |
| Method trên superclass | Không tự dò | Quyết định cách tìm method gốc và xử lý override |
| Class superclass | Không tự dò | Duyệt chain superclass hoặc dùng cơ chế kế thừa thích hợp |
| Interface và interface method | Không tự dò | Duyệt có kiểm soát, đặt tie-break nếu nhiều interface |
| Package/module-level | Không tự dò | Định nghĩa cấp fallback riêng khi cần |

### 7.1. `@Inherited` không phải luật ưu tiên tổng quát

`@Inherited` chỉ ảnh hưởng việc truy vấn annotation loại tương ứng trên **class**, theo chuỗi superclass và quy tắc của Java, khi annotation type được đánh dấu `@Inherited`. Nó không khiến method override tự nhận annotation của method cha và không truyền annotation từ interface như một luật tổng quát.

Nếu khai báo:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Region {
    String value();
}
~~~

thì `Child.class.getAnnotation(Region.class)` có thể nhận metadata từ superclass khi `Child` không khai báo `@Region`; còn `getDeclaredAnnotation(...)` chỉ xét khai báo trực tiếp. **Không nhầm luật Reflection inheritance với thứ tự ưu tiên do một framework thiết kế**.

### 7.2. Nếu cần fallback đến superclass, viết rõ từng cấp

Một chính sách có thể chọn:

~~~text
method trực tiếp
  > class trực tiếp
  > method cha gần nhất
  > class cha gần nhất
  > cấu hình toàn ứng dụng
  > default DENY
~~~

Nhưng chính sách khác có thể chọn `method cha` trước `class trực tiếp` hoặc ưu tiên annotation trên interface. Bạn phải trả lời:

- Khi một class triển khai hai interface có policy khác nhau, **conflict hay merge**?
- Nếu class con khai báo annotation cùng type nhưng bỏ qua vài element có default, có **ghi đè toàn bộ** hay **merge theo element**? Java annotation defaults mặc định thuộc **annotation type**, không tự lấy element values từ annotation trên class cha.
- Nếu method override có annotation riêng, có phải đó là intentional override của annotation trên method cha?
- Nếu method ở interface và class đều có annotation, ai thắng?
- Nếu không có annotation ở bất cứ đâu, trả gì?

Không mở rộng thuật toán của bài sang hierarchy mà không bổ sung các test này. Chỉ dùng `getAnnotation(...)` trên class cũng không giải được mọi trường hợp interface và method.

## 8. Một chiều nữa: default trong annotation element

Một type có thể khai báo:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RetryPolicy {
    int attempts() default 3;
}
~~~

Đối với một class:

~~~java
@RetryPolicy
class A {}
~~~

`A.class.getAnnotation(RetryPolicy.class)` khác `null` và `attempts()` trả `3`. Còn class không gắn `@RetryPolicy` thì `getAnnotation(...)` trả `null`.

Do đó cần phân biệt:

1. **Annotation bị thiếu**: chưa có `@RetryPolicy` ở vị trí đang xét.
2. **Annotation có mặt nhưng element không ghi**: element `attempts` dùng default `3` từ annotation type.
3. **Annotation có mặt và element được ghi tường minh bằng default**: `@RetryPolicy(attempts = 3)`. Với Reflection trên annotation instance, giá trị hiệu lực của hai cách 2 và 3 đều là `3`.

Nếu muốn phân biệt element do tác giả source **ghi trực tiếp** hay nhận từ default, runtime Reflection thông thường trên annotation instance không dành để giữ thông tin đó. Trong annotation processing, `AnnotationMirror.getElementValues()` và `Elements.getElementValuesWithDefaults(...)` có thể giúp phân biệt explicit/default trong mô hình compile-time.

Điều này quan trọng khi thiết kế override/merge: khi annotation ở method có vài element không ghi, đừng tự nghĩ các element còn lại được “thừa kế” từ annotation ở class. Theo ngữ nghĩa Java, chúng lấy default của annotation type **trừ khi mã xử lý của bạn định nghĩa và hiện thực một quy tắc merge bổ sung**.

## 9. Chọn hành vi khi thiếu annotation

Một lựa chọn duy nhất không phù hợp mọi bài toán. Hãy quyết định dựa trên nguy cơ của hành vi:

| Lĩnh vực | Chiến lược missing phổ biến cần cân nhắc | Lý do |
| --- | --- | --- |
| Quyền truy cập hoặc xử lý dữ liệu nhạy cảm | **Fail-closed**, deny khi không có policy; có thể yêu cầu annotation bắt buộc | Tránh cấp quyền do bỏ sót metadata |
| Mapping bắt buộc / cấu hình schema | **Fail-fast**, báo diagnostic hoặc exception về cấu hình | Thiếu metadata khiến ánh xạ không xác định |
| Optional logging/metrics | Dùng **default rõ ràng** như không log đặc biệt | Annotation bổ sung chức năng, thiếu không nhất thiết là lỗi |
| Test discovery | Không có test annotation thì không đăng ký thành test | Không tự suy ra mọi method đều là test |
| Serialization với chiến lược convention | Có thể fallback theo tên field hoặc mặc định tài liệu hóa | Tránh bắt người dùng ghi quá nhiều annotation |
| Dependency injection | Tùy container: có thể tìm quy tắc khác hoặc báo missing dependency | Hành vi cần được định nghĩa chính xác theo framework |

**Fail-open** (cho phép khi thiếu) là lựa chọn cần được xem xét đặc biệt cẩn thận trong hệ thống quyền truy cập. Demo đặt `DENY@default` để minh họa cách an toàn theo hướng không cấp quyền từ sự vắng mặt của annotation.

Nếu hệ thống bắt buộc mỗi method phải tuyên bố policy, `required=true` trong ví dụ làm missing trở thành lỗi. Đó là cách *fail-fast*; với hệ thống thật nên phát hiện ở bước khởi động hoặc compile-time để không đến lúc có request mới vỡ.

### Có nên dùng một annotation `@Default` ở cấp class?

Một chiến lược hợp lệ là khai báo annotation `@DefaultAccess(...)` tại package/module/class, rồi chỉ cho phép method override khi có annotation tường minh. Tuy nhiên, tên và scope phải được công bố rõ; không nên dùng một default “ẩn” khiến người đọc method không đoán được hành vi.

Cũng cần phân biệt **business default** với **Java element default**: `@Roles({"staff"})` là policy class; `roles() default {"user"}` bên trong annotation type là giá trị mặc định **element**. Hai tầng này độc lập.

## 10. Xung đột: báo lỗi, hợp nhất hay ưu tiên?

Có ba chiến lược phổ biến.

### 10.1. Báo lỗi

Chọn khi hai annotation **loại trừ nhau** và không có một lựa chọn an toàn/dễ dự đoán nếu cùng xuất hiện. Ví dụ `@PermitAll` và `@Roles` trên cùng method.

Ưu điểm: dễ kiểm thử, dễ audit; người dùng phải sửa source hoặc cấu hình. Nhược điểm: có thể làm build/startup thất bại; hãy cung cấp thông điệp lỗi nêu rõ vị trí và các annotation xung đột.

### 10.2. Ưu tiên

Chọn khi có quan hệ **scope** rõ ràng. Ví dụ method chuyên biệt hơn class, hoặc cấu hình của ứng dụng có mức ưu tiên hơn default. Nên mô tả **thứ tự cố định** thay vì “annotation nào Reflection trả trước”.

Ở các hệ thống phức tạp, nên tính thêm rule “cụ thể hơn” là gì: nested type, overridden method, interface, abstract superclass, mixin, package, module... Không thể suy ra một total order tự nhiên cho mọi tình huống.

### 10.3. Hợp nhất

Chọn khi nhiều annotation có ý nghĩa **cộng dồn**, ví dụ nhiều tag mô tả một method, nhiều route aliases hoặc nhiều điều kiện filter. Lúc merge cần chỉ rõ:

- **Union hay intersection?** Với quyền truy cập, phép OR và AND có hệ quả khác nhau.
- Thứ tự có ý nghĩa không?
- Có loại bỏ phần tử trùng không?
- Xử lý giá trị rỗng thế nào?
- Nếu một giá trị ghi đè giá trị trước, đâu là tie-break?

Ví dụ, nếu `@Tag("fast")` và `@Tag("unit")` cộng dồn, bạn có thể dùng `@Repeatable` và đọc bằng `getAnnotationsByType(Tag.class)`. Nhưng **`@Repeatable` chỉ cho phép nhiều annotation cùng type; nó không tự chọn union/intersection hay xử lý xung đột nghiệp vụ**.

### Thứ tự giải quyết hợp lý

~~~text
Tập annotation ở từng cấp
       |
       v
Kiểm tra cú pháp/ngữ nghĩa giá trị
       |
       v
Xác định annotation hợp lệ hoặc conflict
       |
       v
Áp dụng quy tắc merge/override/fallback
       |
       v
Nếu vẫn thiếu: default hoặc lỗi
       |
       v
Trả về quyết định + nguồn giải thích
~~~

Đưa “nguồn quyết định” vào output giúp debug, logging và tests. Đừng chỉ trả `true`/`false` nếu hệ thống cần phân tích lý do chọn policy.

## 11. Validation sớm bằng annotation processor

Bài demo dùng Reflection tại runtime để minh họa cấu trúc. Nếu annotation được dùng trên source Java trong project bạn đang xây dựng, một **annotation processor** có thể tìm các vị trí được đánh dấu và báo lỗi trong quá trình biên dịch.

Ý tưởng xử lý:

~~~java
// ĐOẠN MINH HỌA bên trong annotation processor:
for (Element element : roundEnv.getElementsAnnotatedWith(PermitAll.class)) {
    if (element.getAnnotation(Roles.class) != null) {
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR,
                "@PermitAll and @Roles cannot be used together",
                element);
    }
}
~~~

Đây **không** phải file Java chạy độc lập; cần `Processor`/`AbstractProcessor`, `RoundEnvironment`, `Element`, `Diagnostic` và các annotation types liên quan trong project annotation processor.

Điểm khác giữa compile-time và runtime:

- Annotation processor dùng `javax.lang.model.element.Element` và những API mô hình ngôn ngữ, không mặc định dùng `java.lang.reflect.Method` để quan sát source hiện tại.
- Có thể phát hiện cùng vị trí có hai loại annotation và báo lỗi vào đúng class/method.
- Nếu policy bắt buộc cho **mọi method**, chỉ quét các method *đã được gắn annotation* là chưa đủ: processor phải duyệt những method/class trong phạm vi được quản lý và kiểm tra cả **những vị trí không gắn annotation**. Đây là lỗi thiết kế validation rất hay gặp.
- Thường cần kết hợp với build integration/test; không phải mọi class đều nhất thiết được processor xét nếu chỉ xử lý một tập source/module nhất định.
- Annotation `SOURCE` phù hợp nếu chỉ cần compile-time validation; nếu cần runtime Reflection như demo chính, dùng `RUNTIME`.

Với cấu hình bảo mật thực tế, có thể vừa **fail-fast khi startup/compile**, vừa **deny mặc định tại runtime** như hàng rào an toàn. Nhưng không được coi một annotation processor đơn lẻ là bộ máy cấp quyền cho mọi request.

## 12. Những điều cần thận trọng trong thiết kế production

### 12.1. Policy “ALLOW” không đồng nghĩa runtime security

Trong ví dụ, `PolicyResolver.resolve(...)` chỉ trả một `Decision`, **không chặn lời gọi method**. Mã ứng dụng hoặc middleware phải thực thi quyết định, nhận biết user identity/roles và chạy trước logic nhạy cảm. Nếu gọi trực tiếp `Portal.delete()` mà bỏ qua resolver, annotation không tự bảo vệ method.

Ở hệ thống thực tế còn phải xét authentication, authorization, method/proxy invocation, internal calls, caching của policy và hành vi khi resolver ném lỗi. Nên mặc định **từ chối khi có exception phân giải policy** ở lớp thực thi quyền, thay vì cho phép tiếp tục.

### 12.2. Cache policy đúng khóa và tránh mất ngữ cảnh

Nếu runtime resolver tốn chi phí Reflection, có thể cache `Decision` theo **đúng class và method signature**. Không nên cache chỉ theo tên `"delete"` vì hai class khác nhau có thể có method cùng tên, và overload cũng có thể có nhiều method cùng tên nhưng tham số khác nhau.

Ví dụ chính chỉ dùng tên method **không có tham số**, do đó `owner.getDeclaredMethod(methodName)` đủ. Với production nên dùng `Method` hoặc class + method name + parameter types; có thể cần giải quyết bridging/overriding đúng ngữ nghĩa.

### 12.3. Method overload và override

Nếu có:

~~~java
void find(String id) {}
void find(long id) {}
~~~

thì `getDeclaredMethod("find")` không xác định được một trong hai overload vì chúng có tham số. Phải dùng `getDeclaredMethod("find", String.class)` hoặc `getDeclaredMethod("find", long.class)` tương ứng.

Nếu subclass override method, annotation trên method cha **không tự truyền** sang method mới do `@Inherited`. Muốn kiểm tra override inheritance, phải tự duyệt method hierarchy/interface contracts và đưa vào bảng ưu tiên.

### 12.4. Không phụ thuộc vào `@Inherited` một cách vô ý

Trong demo, hai annotation không khai báo `@Inherited` và resolver dùng `getDeclaredAnnotation`, nên kết quả chỉ xét class được truyền và method khai báo trực tiếp. Đổi sang `getAnnotation` mà không đọc kỹ hợp đồng có thể làm policy áp dụng khác khi annotation type về sau được thêm `@Inherited`.

Trước khi thay đổi quy tắc, cần nêu rõ tương thích ngược: annotation đã có trên superclass/interface sẽ ảnh hưởng các subclass/method nào?

### 12.5. Không biến giá trị rỗng thành tín hiệu mập mờ

`@Roles({})` có thể được một framework chọn hiểu là “deny all”; framework khác có thể xem là “để kế thừa class”. Nếu không quy định, người dùng sẽ đoán sai. Trong demo, mảng rỗng là **lỗi** để tránh mơ hồ. Nếu muốn cho phép “deny all” như cấu hình tường minh, có thể tạo annotation riêng `@DenyAll`, rồi bổ sung nó vào cùng tập loại trừ và chính sách giải quyết xung đột.

### 12.6. Không thêm nhiều mức ưu tiên mà thiếu tie-break

Một cây phân giải phức tạp có thể có:

~~~text
annotation method hiện tại
annotation method trên interface A
annotation method trên interface B
annotation class hiện tại
annotation class superclass
annotation global
~~~

Nếu A và B cùng khai báo nhưng khác nhau, không có tự động “interface nào đúng hơn”. Chọn báo ambiguity, chọn một thứ tự xác định có căn cứ, hoặc merge nếu semantics cho phép. Bắt buộc viết test cho diamond inheritance, cùng tên method và source generation.

### 12.7. Mặc định Java element không phải fallback scope

Nhắc lại: một annotation `@RetryPolicy(attempts=...)` với element `attempts() default 3` không tự hòa trộn với annotation trên lớp chứa. Khi method có `@RetryPolicy`, những element không khai báo có giá trị theo default của **annotation type**. Muốn kế thừa từng element từ class, phải thiết kế API biểu diễn “không chỉ định” (có thể dùng sentinel hợp lệ) và code merge; điều đó thường gây thêm phức tạp.

### 12.8. Thay đổi chính sách là thay đổi hợp đồng API

Nếu phiên bản 1 dùng `method > class > deny` mà phiên bản 2 dùng `class > method > allow`, những source annotations không đổi nhưng hành vi thay đổi mạnh. Khi phát hành, hãy coi policy precedence và missing behavior là phần **public contract**: có tài liệu, versioning, migration tests và changelog. Đặc biệt không đổi default deny thành allow mà không đánh giá hậu quả.

## 13. Lỗi phổ biến và cách khắc phục

**Lỗi 1 — Hai annotation cùng cấp, code lấy cái kiểm tra trước.** Điều này làm precedence phụ thuộc thứ tự code, không có quy tắc rõ. Hãy phát hiện conflict và đưa diagnostic hoặc thiết kế thứ tự có tài liệu.

**Lỗi 2 — Thấy method annotation là bỏ qua validation class.** Nếu hợp đồng yêu cầu tất cả metadata khai báo hợp lệ, class conflict phải được phát hiện ngay cả khi method ghi đè. Ví dụ `InvalidClass.action` minh họa.

**Lỗi 3 — “Không annotation” nghĩa là allow.** Với chính sách truy cập, đây thường là hành vi nguy hiểm. Chọn deny mặc định hoặc yêu cầu ghi rõ policy, tùy hệ thống.

**Lỗi 4 — Nhầm `@Roles({})` với không có `@Roles`.** Annotation có mặt nhưng giá trị rỗng là một sự kiện khác missing. Nếu danh sách rỗng không hợp lệ, phải báo lỗi.

**Lỗi 5 — Nghĩ `@Retention(RUNTIME)` quyết định priority.** Retention chỉ kiểm soát việc Reflection đọc được metadata lúc chạy. Resolver phải tự chọn precedence.

**Lỗi 6 — Dựa vào thứ tự trả về của `getAnnotations()`.** API không định nghĩa thứ tự nghiệp vụ để chọn winner. Đọc đúng annotation type và áp luật minh bạch.

**Lỗi 7 — Nghĩ `@Inherited` áp dụng lên overridden method.** Không. `@Inherited` liên quan annotation trên class theo luật cụ thể; method hierarchy cần resolver tự xử lý.

**Lỗi 8 — Lỗi role name bị xem như thiếu.** Với `@Roles({""})` hoặc role không phù hợp, nên fail-fast, không tự fallback để “chạy cho được”.

**Lỗi 9 — Sử dụng một global default ẩn.** Người dùng khó suy đoán hành vi. Hãy document và cho phép quan sát source của quyết định.

**Lỗi 10 — Dùng `Class.getAnnotation` khi muốn khai báo trực tiếp.** Nó có thể xét inheritance với `@Inherited`. `getDeclaredAnnotation` hữu ích khi resolver tự điều khiển search hierarchy.

**Lỗi 11 — Áp dụng policy chỉ lúc scan, không khi thực thi.** Annotation tự thân không chặn lời gọi; nếu đây là access policy, chỗ thực thi phải bắt buộc gọi enforcement.

**Lỗi 12 — Không test cả trường hợp thiếu.** Unit tests thường chỉ có annotated methods nên không phát hiện default sai. Hãy thêm class và method hoàn toàn không annotation.

**Lỗi 13 — Không test conflict ở class khi method có override.** Một resolver có thể vô tình “short-circuit” sớm và bỏ qua lỗi. Hãy test case như `InvalidClass`.

**Lỗi 14 — So sánh policy bằng chuỗi UI thay vì cấu trúc dữ liệu.** Chuỗi `ROLES[staff]` tiện minh họa, nhưng hệ thống lớn nên dùng enum/record bất biến có fields rõ.

## 14. Bài tập tự luyện

1. **Đảo precedence:** Sửa resolver chọn class trước method. Chạy lại và chỉ ra các dòng thay đổi. Thảo luận hậu quả khi class mở nhưng method muốn hạn chế.
2. **Bổ sung deny tường minh:** Tạo `@DenyAll` và sửa `read(...)` để phát hiện tổ hợp cùng cấp với `@PermitAll`/`@Roles`. Quyết định policy của `@DenyAll` khi method ghi đè class.
3. **Missing bắt buộc:** Đặt `required=true` cho mọi method. Dự đoán lỗi với `Unmarked.probe` và lý giải lý do fail-fast.
4. **Role validation:** Thử `@Roles({"Admin"})` hoặc `@Roles({""})`. Hãy giải thích lỗi là `INVALID_ROLES`, không phải `MISSING`.
5. **Class conflict:** Thử hai annotation trên class và một `@Roles` ở method. Quan sát class error vẫn xuất hiện trước khi chọn method.
6. **Method overload:** Tạo hai method `handle(String)` và `handle(int)` với policy khác nhau, đổi resolver nhận đúng parameter types để phân giải Reflection.
7. **Superclass:** Tạo `Base` có `@Roles({"staff"})` và `Child extends Base`. Viết luật mới tra class cha khi class con và method hiện tại thiếu; mô tả cách xử lý khi class con có annotation riêng.
8. **Interface conflict:** Tạo hai interface có method cùng signature nhưng policy khác nhau. Hãy đề xuất ít nhất hai chiến lược (báo ambiguity, ưu tiên có luật, hoặc merge) và đánh đổi của mỗi chiến lược.
9. **Repeatable annotations:** Thiết kế `@Tag` lặp được, đọc bằng `getAnnotationsByType(Tag.class)`; quyết định cách hợp nhất duplicates và thứ tự.
10. **Compile-time validation:** Viết một annotation processor phát hiện `@PermitAll` và `@Roles` cùng cấp. Mở rộng processor để tìm method hoàn toàn không policy khi quy định bắt buộc, thay vì chỉ duyệt annotated methods.
11. **Test matrix:** Dùng JUnit hoặc hàm main để khẳng định 9 dòng stdout của `AccessPolicyDemo.java` như hợp đồng chính thức.
12. **Policy origin:** Mở rộng `Decision` thêm `originClass`, `originMethod`, hoặc enum `Source`. Viết log “policy đến từ đâu” mà không phụ thuộc string message.
13. **Hợp đồng mới:** Chọn một hệ thống không liên quan bảo mật, ví dụ `@Cache(ttl)` và `@NoCache`. Tự lập bảng conflict/precedence/missing rồi viết resolver tương ứng.

## 15. Checklist thiết kế trước khi công bố annotation API

| Câu hỏi | Cần có câu trả lời |
| --- | --- |
| Những annotation types nào loại trừ nhau? | Nêu tập conflict rõ ràng |
| Một cấp có nhiều annotation hợp lệ thì merge hay reject? | Luật cụ thể, không dựa vào thứ tự Reflection |
| Class và method đều có annotation? | Thứ tự ưu tiên được viết thành bảng |
| Method không có annotation? | Có fallback sang class hay không |
| Không cấp nào có annotation? | Default/required/error minh bạch |
| Annotation có giá trị sai/rỗng? | Validate và báo lỗi có vị trí |
| Override có che class conflict không? | Chính sách validation rõ ràng |
| Có dò superclass/interface không? | Scope và quy tắc tie-break xác định |
| Có dùng `@Inherited` không? | Hiểu giới hạn class-only và API tương ứng |
| Annotation elements có default? | Không nhầm element default với fallback của policy |
| Quy tắc áp dụng compile-time hay runtime? | Chọn annotation processor/Reflection phù hợp |
| Nếu policy nhạy cảm? | Enforce ở điểm thực thi; fail-closed khi gặp lỗi |
| Có test toàn bộ ma trận? | Bao gồm missing, invalid, conflict và override |

**Tổng kết:** Thiết kế annotation tốt không chỉ là khai báo `@interface`. Bạn phải xác định rõ **độ ưu tiên giữa các cấp**, **xung đột trong một cấp**, **tình huống thiếu cấu hình**, **giá trị không hợp lệ**, **cách kế thừa** và **thời điểm phát hiện lỗi**. Một resolver nhỏ nhưng có hợp đồng rõ ràng, kiểm thử đầy đủ và không phụ thuộc vào thứ tự ngẫu nhiên sẽ đáng tin cậy hơn nhiều so với một hệ thống dùng hàng loạt `if` không được đặc tả.

### Tài liệu tham khảo

- [Java SE 17 — AnnotatedElement: getAnnotation, getDeclaredAnnotation, getAnnotationsByType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).
- [Java SE 17 — Class: annotation Reflection methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- [Java SE 17 — ElementType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html).
- [Java SE 17 — RetentionPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html).
- [Java SE 17 — Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html).
- [Java SE 17 — RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html).
- [Java Language Specification 17 — `9.6, Annotation Interfaces; `9.7, Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html).
