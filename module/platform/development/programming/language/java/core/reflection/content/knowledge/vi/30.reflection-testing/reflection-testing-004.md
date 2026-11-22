# Kiểm thử invoke với null, varargs, mảng và sai kiểu

## 1. Mục tiêu

**Method.invoke(Object obj, Object... args)** là API của Core Reflection để gọi method tại runtime. Khi kiểm thử công cụ Reflection, bốn nhóm lỗi dễ gặp nhất là truyền **null** không rõ ý nghĩa, xử lý **varargs** và **array** sai, đưa **kiểu/số lượng đối số** không tương thích, và nhầm ngoại lệ do Reflection phát sinh với lỗi do method đích ném.

Người học cần phân biệt hai tầng varargs:

- Tầng Java source: khi gọi **Method.invoke**, compiler quyết định cách đưa đối số vào tham số **Object... args** của chính API này.
- Tầng method đích: Reflection nhận một danh sách đối số; method đích phải nhận đúng số lượng và kiểu theo signature runtime. Reflection không tự gom các chuỗi rời thành một String[] cho method đích khai báo String....

Bài này thực hành trên JDK 17+, không cần Spring, JUnit hoặc thư viện ngoài. Kết quả của chương trình mẫu được đối chiếu với Java runtime.

## 2. Quy tắc Method.invoke

| Thành phần | Quy tắc | Lỗi điển hình |
| --- | --- | --- |
| Receiver cho instance method | Object phải khác null và tương thích với declaring class | NullPointerException nếu null; IllegalArgumentException nếu sai loại |
| Receiver cho static method | Có thể truyền null; object receiver không được dùng | Không yêu cầu tạo instance |
| Danh sách đối số | Đúng số phần tử so với method.getParameterCount() | IllegalArgumentException khi thừa/thiếu |
| Kiểu tham số tham chiếu | Đối số tương thích với kiểu khai báo; null có thể hợp lệ | IllegalArgumentException nếu không thể gán |
| Tham số primitive | Unboxing và widening hợp lệ; không nhận null hoặc narrowing | IllegalArgumentException |
| Method varargs | Một formal parameter cuối có kiểu mảng | Reflection không tự đóng gói các đối số rời |
| Giá trị trả về | Primitive được boxing; void trả null qua invoke | Không suy diễn void thành một đối tượng khác |
| Method body ném Throwable | Reflection bọc Throwable do method đích ném | InvocationTargetException với getCause() |
| Quyền truy cập | Access checks vẫn áp dụng | IllegalAccessException |

**Tra cứu method và gọi method là hai việc khác nhau.** Ví dụ một method khai báo **triple(int)** được tìm bằng **getMethod("triple", int.class)**; dùng **Integer.class** sẽ ném **NoSuchMethodException** ở bước tra cứu. Nhưng khi đã có đối tượng Method cho triple(int), truyền một **Integer** đúng kiểu wrapper có thể được unbox để gọi method đích.

## 3. Null: receiver, một đối số null, mảng đối số null

Xét **String accept(String value)** và đối tượng **target** phù hợp.

| Cách gọi | Số đối số của method đích | Kết quả |
| --- | --- | --- |
| **accept.invoke(target, (Object) null)** | 1 đối số giá trị null | Hợp lệ cho String |
| **accept.invoke(target, new Object[]{null})** | 1 đối số giá trị null | Hợp lệ cho String |
| **accept.invoke(target, (Object[]) null)** | 0 đối số | IllegalArgumentException vì thiếu |
| **accept.invoke(target)** | 0 đối số | IllegalArgumentException |
| **accept.invoke(null, "hi")** | Receiver null, không phải argument null | NullPointerException |
| **accept.invoke("wrong receiver", "hi")** | Receiver không phải Target | IllegalArgumentException |
| **ping.invoke(null)** với static ping() | Không đối số, static | Thành công |

**(Object) null** được compiler xử lý thành **một phần tử** trong danh sách varargs Object[] của Method.invoke. **(Object[]) null** là **cả mảng** danh sách đối số null và được diễn giải như không có đối số. Viết **invoke(target, null)** mà không có cast có thể gây cảnh báo hoặc làm người đọc không hiểu bạn muốn cách nào. Trong thư viện, hãy dùng **new Object[]{null}** khi muốn một tham số null.

Đối với method không có tham số, **invoke(target)** hay **invoke(target, (Object[]) null)** đều biểu diễn lời gọi không đối số. Đối với tham số **int**, kể cả **(Object) null** cũng không hợp lệ vì int là primitive.

## 4. Varargs của method đích khác varargs của Method.invoke

Phương thức khai báo:

~~~java
public String join(String... parts) {
    return parts == null
            ? "array=<null>"
            : String.join("|", parts);
}
~~~

có signature runtime **join(String[])**, nghĩa là chỉ **một tham số hình thức**. Đối tượng Method được tra cứu như sau:

~~~java
Method join = Target.class.getMethod("join", String[].class);
~~~

Đây là các đoạn minh họa; class Target đầy đủ nằm ở phần 7.

| Lời gọi | Diễn giải | Kết quả |
| --- | --- | --- |
| **join.invoke(target, "A", "B")** | Hai String rời; method cần một String[] | IllegalArgumentException |
| **join.invoke(target, (Object) new String[]{"A", "B"})** | Một đối số String[] | Chuỗi A nối B bằng ký tự &#124; |
| **join.invoke(target, new Object[]{new String[]{"A", "B"}})** | Object[] ngoài cùng có một phần tử String[] | Thành công |
| **join.invoke(target, (Object[]) new String[]{"A", "B"})** | String[] được dùng như Object[] chứa hai đối số | IllegalArgumentException |
| **join.invoke(target, (Object) new String[0])** | Một đối số là mảng rỗng | Chuỗi rỗng |
| **join.invoke(target, (Object) null)** | Một đối số String[] có giá trị null | Trả array=<null> |
| **join.invoke(target, (Object) new int[]{1, 2})** | Một int[] không tương thích String[] | IllegalArgumentException |

**Bẫy array covariance:** String[] là subtype của Object[]. Viết trực tiếp **join.invoke(target, new String[]{"A","B"})** có thể khiến compiler dùng chính String[] làm danh sách varargs **Object[]** của API invoke, tức hai đối số; compiler thường cảnh báo cách gọi chưa rõ. Khi muốn truyền **một mảng làm một đối số**, viết **(Object) new String[]{...}** hoặc **new Object[]{new String[]{...}}**.

Không đồng nhất lời gọi **target.join("A","B")** và **join.invoke(target, "A","B")**. Trường hợp thứ nhất được compiler Java đóng gói varargs cho method đích; trường hợp thứ hai Reflection thấy hai argument và không tự gom chúng thành String[].

## 5. Kiểm thử primitive và đối số sai kiểu

Với **int triple(int n)**:

- **Integer.valueOf(4)** được unbox thành int, kết quả 12.
- **Short.valueOf((short) 4)** được unbox thành short rồi widening thành int, kết quả 12.
- **Long.valueOf(4)** không được narrowing từ long thành int, dẫn đến **IllegalArgumentException**.
- **"4"** là String, không tự parse thành int, dẫn đến **IllegalArgumentException**.
- **(Object) null** không thể cung cấp giá trị primitive int, dẫn đến **IllegalArgumentException**.
- Thừa hoặc thiếu số lượng đối số cũng dẫn đến **IllegalArgumentException**.

Reflection không thay thế converter của tầng HTTP/JSON/configuration. Nếu muốn nhận chuỗi "4", hãy parse và validate rõ ràng rồi mới truyền Integer/int phù hợp; đừng kỳ vọng Method.invoke sẽ biến mọi loại input thành kiểu tham số đích.

## 6. Hai tầng lỗi: kiểm tra đối số và code đích

**Lỗi trước khi method body chạy:**

~~~java
triple.invoke(target, "4");
~~~

Reflection từ chối String cho tham số int và ném **IllegalArgumentException trực tiếp**. Nội dung method đích chưa được thực thi.

**Lỗi sau khi method body chạy:**

~~~java
public String fail() {
    throw new IllegalStateException("boom");
}
~~~

Khi gọi **fail.invoke(target)**, Reflection bọc exception từ code đích thành **InvocationTargetException**. Dùng **getCause()** để xem **IllegalStateException("boom")**.

Ngay cả khi method đích tự ném **IllegalArgumentException**, outer exception ở caller Reflection vẫn là **InvocationTargetException**, với cause IllegalArgumentException. Vì thế unit test phải kiểm tra **outer type và cause**, không chỉ tên ngoại lệ cuối cùng.

Ngoài ra, **IllegalAccessException** có thể đến từ kiểm tra quyền, **ExceptionInInitializerError** có thể đến từ khởi tạo class static lỗi, còn **NoClassDefFoundError** có thể là kết quả class lỗi khởi tạo từ lần trước hoặc thiếu dependency. Chúng không đồng nghĩa với lỗi đóng gói đối số.

## 7. Ví dụ Java 17+ đầy đủ: 18 ca kiểm thử

Lưu mã dưới đây thành **InvokeEdgeDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Locale;

public class InvokeEdgeDemo {
    public static class Target {
        public String accept(String s) {
            return s == null ? "<null>" : s.toUpperCase(Locale.ROOT);
        }

        public int triple(int n) {
            return n * 3;
        }

        public String join(String... parts) {
            return parts == null
                    ? "array=<null>"
                    : String.join("|", parts);
        }

        public static String ping() {
            return "pong";
        }

        public String fail() {
            throw new IllegalStateException("boom");
        }
    }

    @FunctionalInterface
    interface Action {
        Object run() throws Throwable;
    }

    static void check(String label, Action action) {
        try {
            System.out.println(label + " -> " + action.run());
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println(label + " -> InvocationTargetException("
                    + cause.getClass().getSimpleName()
                    + ":" + cause.getMessage() + ")");
        } catch (Throwable e) {
            System.out.println(label + " -> "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Target target = new Target();

        Method accept = Target.class.getMethod(
                "accept", String.class);
        Method triple = Target.class.getMethod(
                "triple", int.class);
        Method join = Target.class.getMethod(
                "join", String[].class);
        Method ping = Target.class.getMethod("ping");
        Method fail = Target.class.getMethod("fail");

        check("null value",
                () -> accept.invoke(target, (Object) null));
        check("null args array",
                () -> accept.invoke(target, (Object[]) null));
        check("null receiver",
                () -> accept.invoke(null, "hi"));

        check("static receiver null",
                () -> ping.invoke(null));
        check("static receiver supplied",
                () -> ping.invoke(target));

        check("null for int",
                () -> triple.invoke(target, (Object) null));
        check("short to int",
                () -> triple.invoke(target, Short.valueOf((short) 4)));
        check("wrong type",
                () -> triple.invoke(target, "4"));
        check("wrong count",
                () -> accept.invoke(target));
        check("wrong receiver",
                () -> accept.invoke("not-target", "hi"));

        check("join expanded",
                () -> join.invoke(target, "A", "B"));
        check("join String[] spread",
                () -> join.invoke(
                        target, (Object[]) new String[]{"A", "B"}));
        check("join packed",
                () -> join.invoke(
                        target, (Object) new String[]{"A", "B"}));
        check("join Object[] args",
                () -> join.invoke(target,
                        new Object[]{new String[]{"A", "B"}}));
        check("join wrong array type",
                () -> join.invoke(
                        target, (Object) new int[]{1, 2}));
        check("join null array argument",
                () -> join.invoke(target, (Object) null));
        check("join empty array",
                () -> join.invoke(target, (Object) new String[0]));

        check("target exception",
                () -> fail.invoke(target));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 InvokeEdgeDemo.java
java InvokeEdgeDemo
~~~

Kết quả stdout:

~~~text
null value -> <null>
null args array -> IllegalArgumentException
null receiver -> NullPointerException
static receiver null -> pong
static receiver supplied -> pong
null for int -> IllegalArgumentException
short to int -> 12
wrong type -> IllegalArgumentException
wrong count -> IllegalArgumentException
wrong receiver -> IllegalArgumentException
join expanded -> IllegalArgumentException
join String[] spread -> IllegalArgumentException
join packed -> A|B
join Object[] args -> A|B
join wrong array type -> IllegalArgumentException
join null array argument -> array=<null>
join empty array -> 
target exception -> InvocationTargetException(IllegalStateException:boom)
~~~

**Giải thích output:**
1. **null value** truyền một null cho String, method chạy bình thường; **null args array** đưa danh sách rỗng nên sai số lượng; **null receiver** không có instance hợp lệ.
2. Method **ping** là static nên receiver null hoặc receiver được cung cấp đều không làm thay đổi kết quả.
3. **triple(int)** chỉ chấp nhận tham số tương thích; Short được widened, String và null thì không.
4. **join(String...)** thực tế nhận một String[], nên hai chuỗi rời gây lỗi; hai cách đóng gói bằng **(Object) String[]** và **new Object[]{String[]}** thành công.
5. **join empty array ->** có phần sau mũi tên rỗng vì String.join trên mảng rỗng trả chuỗi rỗng.
6. **target exception** cho biết method body đã chạy và ném IllegalStateException, được Reflection bọc bằng InvocationTargetException.

Ví dụ đã được thực thi bằng JDK và đối chiếu kết quả của toàn bộ 18 tình huống. Chương trình chỉ dùng các tính năng có từ trước Java 17.

### Vấn đề của mảng hai tầng

Hai lời gọi dưới đây có ý nghĩa khác nhau:

~~~java
join.invoke(target, (Object[]) new String[]{"A", "B"});
join.invoke(target, (Object) new String[]{"A", "B"});
~~~

Lời gọi thứ nhất đưa **hai** tham số Reflection; lời gọi thứ hai đưa **một** tham số String[]. Cast ở đây thể hiện ý định, không đơn thuần để compiler hết cảnh báo.

## 8. Viết assertion thay vì chỉ in kết quả

Một chương trình thực hành in output giúp học cơ chế, nhưng test regression nên xác nhận chính xác kết quả hoặc exception. Có thể dùng JUnit 5 nếu dự án có sẵn dependency, hoặc dùng helper Java thuần:

~~~java
@FunctionalInterface
interface ThrowingAction {
    void run() throws Throwable;
}

static <T extends Throwable> T expectThrows(
        Class<T> expected, ThrowingAction action) {
    try {
        action.run();
    } catch (Throwable actual) {
        if (expected.isInstance(actual)) {
            return expected.cast(actual);
        }
        throw new AssertionError(
                "Expected " + expected.getName()
                + ", actual " + actual.getClass().getName(), actual);
    }
    throw new AssertionError(
            "Expected exception " + expected.getName());
}
~~~

Đây là **đoạn minh họa cần đặt trong class test**, không phải chương trình độc lập. Ví dụ kiểm tra hai tầng lỗi:

~~~java
IllegalArgumentException inputError = expectThrows(
        IllegalArgumentException.class,
        () -> triple.invoke(target, "4"));

InvocationTargetException executionError = expectThrows(
        InvocationTargetException.class,
        () -> fail.invoke(target));

if (!(executionError.getCause() instanceof IllegalStateException)) {
    throw new AssertionError("Unexpected cause");
}
~~~

**Tốt hơn bắt exception chung rồi cho test PASS:** bạn phải assert exception thuộc đúng tầng, giữ cause, và với những ca thành công phải kiểm tra giá trị trả về, không chỉ kiểm tra “không crash”.

| Công đoạn | Kiểm tra quan trọng |
| --- | --- |
| Arrange | Tra đúng Method bằng tên và Class[] tham số; tạo receiver |
| Act | Chuẩn bị chính xác Object[] chứa danh sách đối số |
| Assert | Giá trị trả về, exception trực tiếp, hoặc InvocationTargetException.getCause() |
| Isolation | Test khác nhau không chia sẻ state tùy tiện |
| Portability | Không khóa test vào message/stack trace do JDK có thể thay đổi |

Nếu method có side effect, cần kiểm tra trạng thái trước và sau khi gọi. Nếu chạy trong môi trường module, cần phân biệt lỗi quyền truy cập với lỗi tham số.

## 9. Ma trận test tối thiểu cho một Reflection invoker

| Kịch bản | Input | Kỳ vọng |
| --- | --- | --- |
| Một null cho String | (Object) null | Hợp lệ nếu body xử lý |
| Không có tham số | (Object[]) null cho method cần một tham số | IllegalArgumentException |
| Instance receiver null | receiver null | NullPointerException |
| Static receiver null | receiver null cho static method | Hợp lệ |
| Primitive null | int nhận null | IllegalArgumentException |
| Primitive widening | int nhận Short | Hợp lệ |
| Primitive narrowing | int nhận Long | IllegalArgumentException |
| Sai kiểu | int nhận String | IllegalArgumentException |
| Sai số lượng | String nhận hai/không đối số | IllegalArgumentException |
| Sai receiver | instance method được gọi trên object khác loại | IllegalArgumentException |
| Varargs rời | String[] nhận hai String | IllegalArgumentException |
| Varargs đã đóng gói | String[] nhận đúng một String[] | Hợp lệ |
| Sai mảng | String[] nhận int[] | IllegalArgumentException |
| Mảng rỗng | String[] nhận String[0] như một Object | Hợp lệ |
| Mảng null | String[] nhận một null | Body nhận null |
| Method body lỗi | target ném IllegalStateException | InvocationTargetException chứa cause |
| Method trả void | không có kết quả | invoke trả null |
| Lookup sai signature | tìm int method bằng Integer.class | NoSuchMethodException trước invoke |

Đừng dùng **getMethod** với chữ ký không chắc chắn rồi gọi thử một loạt kiểu ngẫu nhiên. Xác định được overload nào cần dùng trước, sau đó mới kiểm tra kiểu và số lượng đối số.

## 10. Bài tập

1. **Varargs primitive:** thêm **sum(int... values)**. So sánh **(Object) new int[]{1,2}** với truyền hai giá trị Integer rời vào invoke.
2. **Mảng hai chiều:** thêm **rows(String[][] data)**; thử truyền **(Object) new String[][]{...}** và cách vô tình coi mảng hai chiều như Object[] danh sách tham số.
3. **Overload:** thêm **handle(String)** và **handle(Integer)**, xác nhận getMethod cần đúng Class type. Reflection không tự chọn overload mới khi invoke.
4. **Cause:** để method body ném **IllegalArgumentException("from target")**. So sánh wrapper InvocationTargetException với lỗi IllegalArgumentException do input sai.
5. **Void return:** thêm method void cập nhật trạng thái rồi kiểm tra giá trị từ invoke là null và side effect đúng.
6. **Empty/null array:** phân biệt **new String[0]** và **(Object) null** cho formal String[]; giải thích vì sao target có thể phản ứng khác nhau.
7. **Test helper:** viết hàm chuẩn bị Object[] từ dữ liệu người dùng theo Class[] của Method, kiểm tra null primitive, số lượng và kiểu mảng trước khi gọi Reflection.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao **(Object) null** khác **(Object[]) null**?  
**Đáp án:** Một bên là một đối số null; bên kia là danh sách đối số null, được xem như không có đối số.

**Câu 2.** Method **join(String...)** có bao nhiêu tham số ở runtime?  
**Đáp án:** Một tham số kiểu String[].

**Câu 3.** Vì sao **join.invoke(target, "A","B")** sai?  
**Đáp án:** Reflection thấy hai đối số trong khi method đích cần một String[].

**Câu 4.** Method nhận int có chấp nhận Short không?  
**Đáp án:** Có, nhờ unboxing và primitive widening sang int.

**Câu 5.** Method nhận int có chấp nhận null không?  
**Đáp án:** Không, IllegalArgumentException.

**Câu 6.** Target tự ném IllegalStateException thì caller Method.invoke nhận gì?  
**Đáp án:** InvocationTargetException, với cause IllegalStateException.

**Câu 7.** Null receiver có hợp lệ với instance method không?  
**Đáp án:** Không; thường ném NullPointerException. Với static method, receiver null là phù hợp.

**Tiêu chí hoàn thành:** tự dự đoán được toàn bộ stdout ví dụ, giải thích hai tầng varargs, phân biệt null receiver/argument và viết test xác nhận đúng exception/cause.

## 12. Tài liệu chuẩn

- [Javadoc Java SE 21 — Method.invoke](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Javadoc Java SE 21 — InvocationTargetException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [Java Language Specification §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12)
- [Javadoc Java SE 21 — Executable.isVarArgs](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html#isVarArgs())

**Nguyên tắc cuối cùng:** chuẩn bị đúng **mảng Object[] danh sách đối số**, kể cả khi **một phần tử trong danh sách cũng chính là một mảng**.