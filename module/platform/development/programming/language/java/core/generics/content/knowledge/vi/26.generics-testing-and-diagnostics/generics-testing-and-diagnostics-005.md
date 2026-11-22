# Kiểm thử heap pollution và thời điểm phát sinh ClassCastException trong Java Generics

## 1. Tại sao code generic có thể biên dịch, ghi dữ liệu sai kiểu mà chưa ném lỗi?

Java Generics giúp kiểm tra kiểu ở **compile time**, nhưng phần lớn generic type arguments bị xóa bởi **type erasure**. Khi chương trình dùng raw types, unchecked casts, varargs có component không reifiable hoặc các đường alias không an toàn, một collection có thể chứa dữ liệu **không phù hợp với kiểu mà chương trình đang tin tưởng**.

Hiện tượng đó gọi là **heap pollution**. Một ví dụ quan trọng:

~~~java
List<String> names = new ArrayList<>(List.of("safe"));

List raw = names;
raw.add(42); // Biên dịch có warning; thường chưa ném exception.

Object value = names.get(1); // Đọc dưới Object: có thể thành công.
String name = names.get(1);  // ClassCastException khi dùng như String.
~~~

Điểm bất ngờ: không nhất thiết xảy ra lỗi tại `raw.add(42)`. Raw alias cho phép gọi `add` mà không có ràng buộc String ở compile time. Đối tượng thực được thêm là Integer, và `ArrayList` không kiểm tra generic argument String ở runtime.

Lỗi xuất hiện khi một chỗ dùng tiếp theo **đòi coi Integer đó là String**. Javac thường chèn `checkcast java/lang/String` ở đường đọc typed value; JVM thực hiện cast này và phát `ClassCastException`.

Vì thế khi kiểm thử generic code cần tách ít nhất bốn thời điểm:

1. **Biên dịch:** có rawtypes/unchecked warnings hay compile errors?
2. **Tạo đường alias/cast:** phép cast kiểm tra runtime class nào, và đã kiểm tra generic arguments chưa?
3. **Ghi dữ liệu:** array/list implementation có chặn kiểu phần tử ở đây không?
4. **Đọc/sử dụng typed value:** JVM có cần thực hiện cast xuống kiểu cụ thể và ném ClassCastException không?

**Mục tiêu kiểm thử không phải chỉ hỏi “có ném ClassCastException không?” mà phải xác định “ở thao tác nào, vì cơ chế kiểm tra kiểu nào, và với điều kiện gì?”**

## 2. Ba khái niệm không nên trộn lẫn

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Unchecked warning** | Compiler không chứng minh được an toàn generic của một phép gán/gọi/cast. | `raw.add(42)`; `(List<String>) unknown` |
| **Heap pollution** | Một tham chiếu kiểu tham số hóa được dùng với object/dữ liệu không thỏa cam kết kiểu. | `List<String>` bị ghi Integer qua raw alias. |
| **ClassCastException** | Runtime cast tới class/interface đích thất bại. | Đọc Integer thành String. |

Một **warning** chưa chứng minh thực tế đã có dữ liệu sai. Một **unchecked cast** có thể thành công về mặt runtime class nhưng vẫn tiềm ẩn sai generic argument. Một list đã bị pollution cũng có thể tiếp tục hoạt động ở một số phép đọc như `size()` hoặc đọc trực tiếp vào Object, rồi chỉ thất bại nhiều bước sau khi giá trị phải trở thành String.

Bởi vậy:
- **Compile success** không chứng minh dữ liệu hợp kiểu.
- **Không thấy exception khi ghi** không chứng minh phép ghi an toàn.
- **Có warning** không chứng minh tất cả lời gọi chắc chắn ném exception.
- **Có ClassCastException** không nhất thiết chứng minh nguyên nhân là heap pollution; một checked cast sai lớp thông thường cũng gây ClassCastException.

Các khẳng định trong bài được minh họa và kiểm chứng qua chương trình Java 17 đầy đủ ở phần 9.

## 3. Type erasure giải thích điều gì?

Với một collection:

~~~java
List<String> strings = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
~~~

cả hai có thể dùng cùng runtime class `java.util.ArrayList`. JVM không tạo `ArrayList<String>` và `ArrayList<Integer>` thành hai class runtime độc lập tương ứng với type arguments.

`List<E>.get(int)` về bytecode trả đối tượng theo kiểu erased `Object`. Khi caller viết:

~~~java
String s = strings.get(0);
~~~

javac biết ở source rằng `strings` là List<String>, nên có thể tạo code tương ứng:

~~~text
invokeinterface java/util/List.get:(I)Ljava/lang/Object;
checkcast java/lang/String
astore ...
~~~

Đây là minh họa **dạng bytecode**, không phải offset lệnh cố định. Cast bổ sung sau lời gọi `get` kiểm tra object thực sự có thể dùng như String không.

Trong khi đó:

~~~java
Object o = strings.get(0);
~~~

không cần cast từ Object xuống String để đáp ứng biến đích. Nếu phần tử là Integer do pollution, phép đọc thành Object vẫn hợp lệ.

**Thời điểm lỗi phụ thuộc vào ngữ cảnh cần kiểu đích.** Một phép gọi method, assignment, return, method reference hoặc lambda có thể buộc compiler/JVM kiểm tra kiểu khác nhau. Đừng hứa rằng “mỗi lần gọi get đều ném ngay” hoặc rằng “mọi lời gọi get đều an toàn”.

### Vì sao ArrayList.add không tự kiểm tra generic E?

Ở bytecode, generic `E` đã bị erasure (thường là Object trong Collection). `ArrayList.add(Object)` xử lý object reference; nó không có runtime class token String gắn riêng với mỗi List<String> để kiểm tra phần tử thêm vào.

Ngược lại, một wrapper được tạo với token `String.class` có thể chủ động kiểm tra lúc ghi; xem `Collections.checkedList` ở phần 12.

## 4. Kịch bản 1: pollution thông qua raw List

Một raw alias làm mất type arguments:

~~~java
List<String> names = new ArrayList<>(List.of("safe"));

List raw = names;
raw.add(42);
~~~

Compiler, khi bật `-Xlint:rawtypes,unchecked`, có thể báo:
- `[rawtypes] found raw type: List` tại khai báo `List raw`.
- `[unchecked] unchecked call to add(E)` tại `raw.add(42)`.

Nhưng Java giữ khả năng dùng raw types để tương thích với code cũ. Compiler warning không biến thành runtime guard tự động.

Sau phép ghi:

~~~java
System.out.println(names.size()); // 2
~~~

vẫn có thể chạy bình thường vì tính độ dài không đòi đọc Integer dưới dạng String.

Một phép đọc:

~~~java
Object second = names.get(1); // Integer object được nhìn như Object.
~~~

cũng có thể thành công.

Nhưng:

~~~java
String second = names.get(1); // ClassCastException.
~~~

khi JVM cần cast kết quả về String, Integer không tương thích và exception xuất hiện.

**Test đúng:** đặt assertion/exception expectation tại typed read, đồng thời kiểm tra các bước trước thực sự đã xảy ra mà không ném exception. Nếu test chỉ bọc cả phương thức từ đầu đến cuối bằng `expectClassCast`, ta biết có lỗi nhưng không biết nó xuất hiện ngay lúc write hay sau một read.

### 4.1. Chỗ sai nằm ở đâu?

Lỗi thiết kế nằm ở đường **ghi không an toàn qua raw alias**. Typed read là điểm lỗi **bộc lộ**. Stack trace thường trỏ tới typed read, nhưng hành vi gây pollution có thể đã diễn ra nhiều lời gọi trước và ở một lớp khác.

Khi debug, tìm cả nơi exception xuất hiện lẫn đường dữ liệu được thêm vào collection. Fix thực tế nên chặn raw/unchecked writes ở biên, không chỉ catch ClassCastException tại mọi nơi đọc.

## 5. Kịch bản 2: unchecked cast kiểm tra raw class, không kiểm tra type argument

Ví dụ:

~~~java
Object unknown = List.of(7);

List<String> forged = (List<String>) unknown;
~~~

Với `-Xlint:unchecked`, compiler báo **unchecked cast**. Ở runtime, object là một List nên bước kiểm tra class/interface List thành công. JVM **không duyệt danh sách để xác minh các phần tử là String**.

Những thao tác sau vẫn có thể chạy:

~~~java
int size = forged.size();     // 1.
Object first = forged.get(0); // Integer nhưng đích là Object.
~~~

Trong khi:

~~~java
String first = forged.get(0); // ClassCastException.
~~~

Cần phân biệt hai điều:
- Một cast từ Object sang `List<String>` **vẫn có thể ném ClassCastException ngay tại cast** nếu object thực tế hoàn toàn không phải List, ví dụ `"hello"`.
- Nếu object thực tế là List nhưng có phần tử không phải String, phần **raw class check** có thể qua, còn generic element type chưa được xác minh. Lỗi sau đó xảy ra khi phần tử bị dùng như String.

Vì vậy câu “unchecked cast **luôn** đợi đến lúc đọc phần tử mới lỗi” cũng sai. Thời điểm còn phụ thuộc **object có vượt qua kiểm tra raw type hay không**.

### 5.1. List<?> không khẳng định type argument String

Khi chưa xác minh dữ liệu, có thể giữ nó trong một biến với hợp đồng trung thực hơn:

~~~java
if (unknown instanceof List<?> candidates) {
    for (Object candidate : candidates) {
        System.out.println(candidate);
    }
}
~~~

`instanceof List<?>` kiểm tra runtime List thích hợp, nhưng **không chứng minh List<String>**. Cần duyệt và kiểm tra từng phần tử nếu sẽ công bố kết quả dưới dạng List<String>.

## 6. Kịch bản 3: generic varargs và array backing

Varargs `T...` được biểu diễn bằng một **array**. Vấn đề xuất hiện với kiểu phần tử không reifiable, ví dụ `List<String>`:

~~~java
static void unsafeVarargs(List<String>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(99);
}
~~~

Java không cho tạo một generic array trực tiếp bằng biểu thức:

~~~java
// List<String>[] array = new List<String>[2];
// Compile error: generic array creation.
~~~

Tuy nhiên, khai báo `List<String>...` hợp lệ và lời gọi:

~~~java
unsafeVarargs(List.of("before"));
~~~

được phép có **unchecked varargs warnings**. Compiler chuẩn bị một array có runtime component type `List`, không thể tạo một component class List<String> riêng vì type arguments không reifiable.

Trong method:
- `groups` có kiểu tĩnh `List<String>[]`.
- `groups.getClass().getComponentType()` có thể là `List.class` khi compiler tạo backing `List[]`.
- `Object[] alias = groups` hợp lệ vì Java arrays covariant.
- `alias[0] = List.of(99)` có thể qua runtime array-store check vì giá trị vẫn là List.
- `groups[0].get(0)` trả Integer thực tế, nhưng typed read như String về sau có thể gây ClassCastException.

Một phép kiểm tra như `groups[0].size()` hoặc `Object x = groups[0].get(0)` không buộc có cast xuống String, nên có thể chạy trước khi lỗi xảy ra.

### 6.1. Vì sao đây là heap pollution đặc trưng của generic varargs?

Java arrays **reifiable** ở mức runtime component class: List[] biết “mỗi phần tử phải là List”, nhưng không biết phần tử thứ nhất phải là List<String> và phần tử thứ hai cũng phải là List<String>.

Do đó array backing cho `List<String>...` cho phép một object `List<Integer>` vượt qua kiểm tra component List. Lỗi không nằm ở `List.of(99)` tự nó; đây là một List<Integer> hoàn toàn hợp lệ. Lỗi ở việc gán nó vào vị trí mà chương trình đang đối xử như List<String>.

### 6.2. Cảnh báo compiler nào cần xem?

Với:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked,varargs HeapPollutionTest.java
~~~

Ở ví dụ không đánh dấu an toàn, javac phát các thông điệp đại ý:

~~~text
[unchecked] Possible heap pollution from parameterized vararg type List<String>
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
~~~

Hai warning này thuộc category `unchecked`, dù tên có chữ varargs. `-Xlint:varargs` cũng hữu ích khi kiểm tra những thao tác dùng backing array trong method gắn `@SafeVarargs` nhưng vẫn làm lộ array. Đừng nhầm tên thông điệp với tên category.

## 7. Kịch bản 4: tại sao String[] phát ArrayStoreException sớm hơn?

Một Java array cụ thể **biết runtime component class**:

~~~java
String[] textArray = {"ok"};
Object[] alias = textArray;

alias[0] = 99; // ArrayStoreException ngay ở phép ghi.
~~~

Ở runtime, object array thật là `String[]`. JVM kiểm tra phần tử sắp ghi có tương thích với String không, nên từ chối Integer ngay tại `aastore`.

So sánh:

| Trường hợp | Component runtime | Ghi sai | Lỗi thường xuất hiện |
| --- | --- | --- | --- |
| `String[]` qua `Object[]` alias | `String` | Ghi Integer | **ArrayStoreException tại write**. |
| `List<String>[]` backing từ varargs | `List` | Ghi `List<Integer>` | Có thể **không lỗi tại write**; typed read về sau có thể CCE. |
| `List<String>` qua raw `List` alias | Không có runtime String element type trên ArrayList | `add(Integer)` | Có thể **không lỗi tại write**; typed read về sau có thể CCE. |
| `Collections.checkedList(...,String.class)` qua chính wrapper | Wrapper mang `String.class` token | `add(Integer)` | **ClassCastException tại write qua wrapper**. |

Vì sao array generic không được tạo trực tiếp theo kiểu `new List<String>[2]`? Nếu nó được cho phép như một array thật nhưng chỉ reify raw List, những cam kết về generic argument có thể dễ dàng bị phá bởi array covariance. Việc cấm generic array creation với non-reifiable component type giúp giảm các đường type-unsafe, trong khi cơ chế varargs vẫn cần hỗ trợ source syntax và có cảnh báo thích hợp.

## 8. Thiết kế test: xác nhận cả **không lỗi sớm** lẫn **lỗi đúng điểm**

Một test không tốt chỉ viết:

~~~java
try {
    doEverything();
} catch (ClassCastException e) {
    // coi là pass
}
~~~

Cách này không biết exception xảy ra tại:
- Cast ban đầu;
- Thao tác ghi qua wrapper;
- Typed read;
- Một method reference/lambda;
- Một bridge method;
- Hay một đoạn code hoàn toàn không liên quan.

Một test tốt cần chia thành các assertions rõ:
1. Ghi qua raw alias đã thực hiện.
2. Kích thước/data thực tế cho thấy có phần tử sai kiểu.
3. Đọc như Object thành công.
4. Chính assignment vào String phát ClassCastException.
5. Với array String[], ghi qua Object[] phát ArrayStoreException **ngay tại write**.
6. Với checkedList, ghi sai qua wrapper phát ClassCastException **ngay tại write**.
7. Validator ở biên từ chối dữ liệu sai và chỉ trả typed copy sau kiểm tra.

Dùng một helper dạng `expect(Class<? extends Throwable>,Runnable,String)` có thể phân biệt chính xác exception type và vị trí được bọc. Không chỉ kiểm tra “có Exception nào đó”: ClassCastException, ArrayStoreException, IllegalArgumentException và AssertionError mang ý nghĩa khác nhau.

### 8.1. Test nên fail khi không có exception như mong đợi

Một helper đáng tin phải:
- Gọi đúng operation cần thử.
- Nếu operation **không ném**, ném AssertionError để fail test.
- Nếu ném **đúng expected class**, báo test pass.
- Nếu ném loại khác, **không được nuốt lỗi** mà phải fail.

Trong ví dụ hoàn chỉnh dưới đây, helper so sánh bằng `expected.isInstance(thrown)` và tăng bộ đếm cho từng phép kiểm tra thành công. Nó không phụ thuộc vào Java assertions, vốn bị tắt mặc định nếu không bật `-ea`.

## 9. Chương trình kiểm thử Java 17 đầy đủ, không cần dependency

Lưu nguyên chương trình sau thành **HeapPollutionTest.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class HeapPollutionTest {
    private static int checks;

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
        checks++;
        System.out.println("PASS " + label);
    }

    private static void expect(
            Class<? extends Throwable> expected,
            Runnable action,
            String label) {

        try {
            action.run();
            throw new AssertionError(
                    label + ": expected " + expected.getSimpleName()
            );
        } catch (Throwable thrown) {
            if (!expected.isInstance(thrown)) {
                throw thrown;
            }
            checks++;
            System.out.println(
                    "PASS " + label + " -> "
                            + thrown.getClass().getSimpleName()
            );
        }
    }

    static List<String> validateStrings(List<?> candidates) {
        List<String> clean = new ArrayList<>();

        for (Object value : candidates) {
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException(
                        "Non-string element"
                );
            }
            clean.add(text);
        }

        return List.copyOf(clean);
    }

    // Không an toàn: cố ý minh họa pollution qua List[] backing.
    static void unsafeVarargs(List<String>... groups) {
        check(
                groups.getClass().getComponentType() == List.class,
                "varargs runtime component is List"
        );

        Object[] alias = groups;
        alias[0] = List.of(99);

        check(
                groups[0].size() == 1,
                "varargs polluted without immediate failure"
        );

        Object rawRead = groups[0].get(0);
        check(
                rawRead.equals(99),
                "varargs reading as Object succeeds"
        );

        expect(ClassCastException.class, () -> {
            String value = groups[0].get(0);
            System.out.println(value);
        }, "varargs typed read");
    }

    public static void main(String[] args) {
        // 1. Raw alias: ghi sai nhưng chưa lỗi, typed read mới lỗi.
        List<String> names =
                new ArrayList<>(List.of("safe"));
        List raw = names;
        raw.add(42);

        check(
                names.size() == 2,
                "raw insertion did not throw"
        );

        Object second = names.get(1);
        check(
                second.equals(42),
                "Object read skips String checkcast"
        );

        expect(ClassCastException.class, () -> {
            String text = names.get(1);
            System.out.println(text);
        }, "raw typed read");

        // 2. Unchecked cast từ Object chỉ xác nhận raw List.
        Object unknown = List.of(7);
        List<String> forged = (List<String>) unknown;

        check(
                forged.size() == 1,
                "unchecked cast checked only raw List"
        );

        expect(ClassCastException.class, () -> {
            String text = forged.get(0);
            System.out.println(text);
        }, "unchecked cast typed read");

        // 3. List<String>... mang backing List[].
        unsafeVarargs(List.of("before"));

        // 4. Array reification: lỗi ngay ở phép ghi vào String[].
        String[] textArray = {"ok"};
        Object[] arrayAlias = textArray;

        expect(ArrayStoreException.class, () ->
                        arrayAlias[0] = 99,
                "reified String array write"
        );

        check(
                "ok".equals(textArray[0]),
                "reified array unchanged"
        );

        // 5. Duyệt/kiểm tra ở biên và tạo typed copy.
        expect(IllegalArgumentException.class,
                () -> validateStrings(names),
                "boundary validator rejects corrupted list"
        );

        check(
                validateStrings(List.of("A", "B"))
                        .equals(List.of("A", "B")),
                "validator makes typed copy"
        );

        // 6. Runtime-checked wrapper chặn sai kiểu tại write.
        List<String> guarded = Collections.checkedList(
                new ArrayList<>(), String.class
        );
        List rawGuarded = guarded;

        expect(ClassCastException.class,
                () -> rawGuarded.add(99),
                "checkedList rejects invalid insertion"
        );

        check(
                guarded.isEmpty(),
                "checkedList backing unchanged"
        );

        System.out.println("TOTAL=" + checks);
    }
}
~~~

Biên dịch với các compiler warnings cần quan sát, sau đó chạy:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked,varargs HeapPollutionTest.java
java HeapPollutionTest
~~~

Chương trình **được phép có các unchecked/rawtypes warnings** vì nó cố ý dựng những trường hợp không an toàn nhằm kiểm thử. Trong một ứng dụng production, chúng không phải warning để bỏ qua; trong một bài test giáo dục này, chúng là một phần của đối tượng nghiên cứu.

**Stdout chính xác khi chạy:**

~~~text
PASS raw insertion did not throw
PASS Object read skips String checkcast
PASS raw typed read -> ClassCastException
PASS unchecked cast checked only raw List
PASS unchecked cast typed read -> ClassCastException
PASS varargs runtime component is List
PASS varargs polluted without immediate failure
PASS varargs reading as Object succeeds
PASS varargs typed read -> ClassCastException
PASS reified String array write -> ArrayStoreException
PASS reified array unchanged
PASS boundary validator rejects corrupted list -> IllegalArgumentException
PASS validator makes typed copy
PASS checkedList rejects invalid insertion -> ClassCastException
PASS checkedList backing unchanged
TOTAL=15
~~~

Chương trình dùng **explicit checks và expect** thay cho `assert` nên không cần thêm `-ea`. Nếu một kỳ vọng sai, chương trình ném AssertionError hoặc exception không mong đợi và test thất bại.

### 9.1. Thứ tự 15 lần kiểm tra

**Nhóm raw alias (3 checks):**
1. Raw add không ném.
2. Đọc phần tử Integer qua biến Object thành công.
3. Đọc phần tử đó vào String ném ClassCastException.

**Nhóm unchecked cast (2 checks):**
4. Cast object có runtime type List thành List<String> không xác nhận type argument.
5. Đọc Integer trong list đã cast như String ném ClassCastException.

**Nhóm generic varargs (4 checks):**
6. Runtime array component là List.
7. Đưa List<Integer> vào List[] không ném tức thời.
8. Đọc Integer từ group như Object thành công.
9. Đọc cùng phần tử như String ném ClassCastException.

**Nhóm array reification (2 checks):**
10. Ghi Integer vào runtime String[] qua Object[] ném ArrayStoreException.
11. Array gốc vẫn chứa "ok".

**Nhóm validation (2 checks):**
12. Validator từ chối danh sách đã bị hỏng.
13. Validator chấp nhận và sao chép danh sách toàn String.

**Nhóm checkedList (2 checks):**
14. Raw add sai kiểu qua checked wrapper ném ClassCastException tại write.
15. Wrapper không chứa phần tử sau phép ghi thất bại.

Đây là **một chương trình có các test độc lập ở cấp thao tác**, không phải 15 tệp test riêng. Việc gom test trong một chương trình giúp so sánh thời điểm phát sinh exception bằng cùng một môi trường Java.

## 10. Cảnh báo biên dịch là bằng chứng cần lưu trong kiểm thử

Lệnh:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked,varargs HeapPollutionTest.java
~~~

có thể in những diagnostics với nội dung tiêu biểu:

~~~text
[unchecked] Possible heap pollution from parameterized vararg type List<String>
[rawtypes] found raw type: List
[unchecked] unchecked call to add(E) as a member of the raw type List
[unchecked] unchecked cast
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
~~~

Với bản chương trình này, hai khai báo raw List và hai lời gọi add qua raw receiver làm số warnings nhiều hơn số dòng thông điệp đại diện bên trên. Số thứ tự dòng, đường dẫn và chi tiết tổng số warnings phụ thuộc nguồn và compiler version; hãy quan sát **category và vị trí thao tác** chứ không hard-code toàn bộ compiler stderr như stdout ổn định.

**Phân biệt stderr của javac và stdout của java:**
- Compiler warnings xuất hiện trong giai đoạn **build**.
- Các dòng `PASS` là **kết quả thực thi test**.
- Có warnings chưa có nghĩa javac đã thất bại; bài test này chủ động tạo code compile được nhưng unsafe.
- Nếu dự án bật `-Werror`, warnings khiến build thất bại theo chính sách quality gate; nên tách bài test minh họa unsafe code khỏi production build hoặc sử dụng chiến lược test riêng phù hợp.

Trong môi trường dùng nhiều compiler/language release, việc kiểm tra cả compile diagnostics lẫn runtime behavior giúp phát hiện thay đổi về warning location và logic test.

## 11. Dùng javap tìm điểm checkcast được chèn

Biên dịch:

~~~bash
javac --release 17 -Xlint:unchecked HeapPollutionTest.java
~~~

Kiểm tra bytecode:

~~~bash
javap -c -p HeapPollutionTest
~~~

Những đoạn tương ứng với typed read có thể chứa:

~~~text
invokeinterface java/util/List.get:(I)Ljava/lang/Object;
checkcast     java/lang/String
~~~

Đây là **mẫu lệnh quan trọng**, không phải chuỗi đầy đủ để dò chính xác từng offset trên mọi javac. Chương trình dùng lambda, nên một số `checkcast` có thể nằm trong **synthetic lambda methods** xuất hiện trong output `javap -p -c`.

### 11.1. Phân biệt compile-time generic type và runtime cast

`List<String>` bảo đảm compiler chỉ cho dùng kết quả `get` như String trong code thông thường đã được kiểm tra. Nhưng phần tử thật có thể sai nếu collection bị pollution qua raw/unchecked alias. Khi biến đích hoặc phương thức đòi String, bytecode có `checkcast String`, và JVM kiểm tra dữ liệu thực.

Vì vậy các dòng:

~~~java
Object rawRead = names.get(1);
String typedRead = names.get(1);
~~~

khác nhau về **kiểu đích**. Việc cùng gọi `get` không có nghĩa cùng một loại checkcast được thực hiện.

### 11.2. Stack trace thường chỉ cho biết chỗ lỗi phát hiện

Nếu một List<String> được truyền qua nhiều service rồi mới typed read, stack trace ở ClassCastException thường trỏ tới lúc đọc/cast. Nó chưa trả lời “ai đưa Integer vào List<String>?”. Kiểm thử nên mô hình hóa **đường ghi gây pollution** và **điểm đọc phát hiện sai** như hai sự kiện độc lập.

## 12. Collections.checkedList: chặn lỗi ở biên ghi, nhưng có giới hạn

Java cung cấp một wrapper cho runtime type checking:

~~~java
List<String> checked = Collections.checkedList(
        new ArrayList<>(),
        String.class
);
~~~

Nó giữ một runtime class token String và kiểm tra những element mới được thêm qua **checked wrapper**. Ví dụ:

~~~java
List raw = checked;
raw.add(99); // ClassCastException ngay tại write qua wrapper.
~~~

Trong chương trình hoàn chỉnh, phép thêm này được bọc bằng `expect(ClassCastException.class, ...)` và sau đó test xác nhận checked list vẫn rỗng.

### 12.1. Wrapper không thể loại bỏ mọi alias nguy hiểm

Ví dụ:

~~~java
List<String> backing = new ArrayList<>();
List<String> guarded = Collections.checkedList(
        backing, String.class
);

// Nếu một người giữ raw alias đến chính backing list,
// họ có thể bypass wrapper và đưa object sai vào backing.
~~~

Một checked wrapper chỉ giám sát các mutation đi **qua chính wrapper**. Nó không có khả năng ngăn đường truy cập khác sửa trực tiếp backing collection. Nó cũng không tự sửa phần tử sai kiểu đã có từ trước khi tạo wrapper, và không deep-validate mọi cấu trúc generic lồng nhau.

Bởi vậy nếu dữ liệu đầu vào không đáng tin, tốt hơn nên **kiểm tra và tạo một collection mới** tại ranh giới tin cậy, đồng thời không phát tán mutable alias của collection gốc.

### 12.2. CheckedList là runtime checking, không phải reified List<String>

`Collections.checkedList` dùng token `Class<E>` để kiểm tra đối tượng thêm trực tiếp. Nó không biến toàn bộ Java generics thành reified. Với kiểu phần tử lồng nhau như `List<List<String>>`, chỉ có raw `List.class` không đủ để kiểm tra mọi String trong các list con.

Nếu cần xác thực lồng nhau, hãy tự duyệt các tầng hoặc dùng validator phù hợp với schema nghiệp vụ.

## 13. Xác thực dữ liệu tại biên tốt hơn unchecked cast

Một boundary method có thể nhận `List<?>` và tạo `List<String>` mới:

~~~java
static List<String> validateStrings(List<?> candidates) {
    List<String> clean = new ArrayList<>();

    for (Object value : candidates) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException(
                    "Non-string element"
            );
        }
        clean.add(text);
    }

    return List.copyOf(clean);
}
~~~

Đây là Java 17 code: pattern matching `instanceof String text` giúp kiểm tra runtime class của từng phần tử. Nếu phần tử không phải String (kể cả null), method ném IllegalArgumentException theo chính sách đã chọn.

**Tại sao chỉ cast hoặc copy chưa đủ?**

~~~java
// Không xác minh String elements:
List<String> forged = (List<String>) unknown;

// Sao chép qua constructor/copyOf không tự xác minh từng E:
// nếu nguồn đã bị pollution, chỉ copy có thể giữ dữ liệu sai.
~~~

Một constructor collection chỉ sao chép phần tử theo kiểu runtime Object của implementation; nó không có class token String tự động trong generics. Đối với boundary chưa tin cậy, **validate từng phần tử rồi mới xây typed copy**.

### 13.1. Quy tắc của List.copyOf

`List.copyOf(clean)` trả List không cho sửa đổi qua API thông thường. Nó là một **shallow copy**: nếu element là object mutable, copy không tự làm các object bên trong trở thành immutable. `List.copyOf` cũng từ chối null elements theo hợp đồng. Trong ví dụ trên, null đã bị loại bởi pattern check trước đó.

Không nên nói `List.copyOf` tự động “sửa heap pollution”. Nó hữu ích để ngắt đường chia sẻ mutable alias **sau khi dữ liệu đã được xác thực**.

## 14. @SafeVarargs không phải cách sửa một method thực sự unsafe

Một số APIs varargs generic là an toàn nếu chúng chỉ đọc các phần tử đúng cách và không ghi/làm lộ mảng backing. Java cho phép tác giả đặt `@SafeVarargs` trên các khai báo phù hợp (constructors, static/final/private varargs methods) để cam kết triển khai không thực hiện thao tác varargs unsafe.

Ví dụ phương thức có thể chứng minh an toàn khi chỉ đọc và tạo List mới:

~~~java
@SafeVarargs
static <T> List<T> copyValues(T... values) {
    List<T> result = new ArrayList<>();
    for (T value : values) {
        result.add(value);
    }
    return List.copyOf(result);
}
~~~

Đoạn code giả định import `java.util.List` và `java.util.ArrayList`; phương thức có thể đặt trong một class. Nó không làm lộ backing array và không ghi loại khác vào mảng.

Nhưng phương thức `unsafeVarargs` trong chương trình test cố ý thực hiện:

~~~java
Object[] alias = groups;
alias[0] = List.of(99);
~~~

Đặt `@SafeVarargs` lên method đó **không biến nó thành an toàn**; chỉ có thể giấu một số warnings ở call sites và tuyên bố sai hợp đồng. Runtime vẫn có thể xảy ra heap pollution và ClassCastException.

Nếu muốn test được sự phát hiện lỗi, hãy giữ unsafe version riêng trong test code, đừng annotate nó để làm compile output đẹp.

## 15. Khi nào exception có thể xuất hiện sớm hoặc muộn hơn?

Một bảng thời điểm phát hiện:

| Thao tác | Điều kiện | Kết quả cần kiểm thử |
| --- | --- | --- |
| Cast Object sang String | Object thật là Integer | ClassCastException **ngay tại cast**. |
| Cast Object chứa một List<Integer> sang List<String> | Object runtime là List | Raw List cast có thể qua; generic elements chưa được xác thực. |
| Raw `add(Integer)` vào ArrayList có typed alias List<String> | Không có checked wrapper/token | Có thể qua; typed read về sau mới fail. |
| `String s = names.get(1)` sau pollution | Phần tử thực là Integer | ClassCastException tại typed read/inserted checkcast. |
| `Object o = names.get(1)` | Phần tử thực là Integer | Không cần cast thành String; có thể qua. |
| `alias[0] = 99` với alias trỏ tới String[] | Runtime component String | ArrayStoreException **ngay tại write**. |
| `alias[0] = List.of(99)` với alias trỏ tới List[] | Runtime component List | Qua array store check; typed read sau có thể fail. |
| Raw add qua Collections.checkedList với token String | Wrapper thật kiểm tra từng insertion | ClassCastException **ngay tại write qua wrapper**. |
| Validate List<?> với từng phần tử | Encounter Integer khi yêu cầu String | Validator có thể ném IllegalArgumentException theo chính sách tại biên. |

Không mặc định **mọi ClassCastException đều đến sau**; cast thành một runtime class không tương thích có thể thất bại ngay. Điều được nghiên cứu là **generic type argument check bị trì hoãn/không có ở chỗ tạo alias hoặc chỗ ghi**, sau đó một typed use mới phát hiện mismatch.

### 15.1. Nếu code không bao giờ đọc theo String thì sao?

Một polluted List<String> có thể tồn tại lâu mà chưa gây ClassCastException nếu chỉ:
- Kiểm tra `size()`.
- Di chuyển reference.
- Xóa phần tử theo chỉ số.
- Đọc một giá trị vào Object rồi không ép thành String.

Nhưng dữ liệu vẫn không thỏa cam kết API. **Không thấy exception không biến cấu trúc đó thành an toàn.** Một thay đổi code sau này thêm map(String::length) hoặc đọc vào String có thể kích hoạt lỗi đã bị che giấu từ trước.

### 15.2. Đọc qua lambda, iterator hay stream cũng có thể là điểm phát hiện

Một Consumer/String lambda có kiểu đầu vào String. Khi dùng nó với polluted List<String>, điểm xử lý phần tử có thể buộc một cast thành String. Do đó exception không nhất thiết xuất hiện trực tiếp ở source có dạng `String s = list.get(0)`; nó có thể nằm trong generated lambda adapter hoặc code đọc của một thư viện.

Để chẩn đoán tốt, tìm chỗ **kiểu đích được yêu cầu** và đối chiếu với generic source data. Javap và stack trace hỗ trợ tìm vị trí nhưng vẫn cần truy đường ghi.

## 16. Phân biệt heap pollution với một cast sai thông thường

Một ClassCastException thuần túy:

~~~java
Object value = Integer.valueOf(10);
String text = (String) value; // ClassCastException trực tiếp.
~~~

Không có generic collection hay raw type; đây là một runtime cast sai kiểu bình thường. Không nên gắn nhãn heap pollution chỉ vì thấy ClassCastException.

Ngược lại, **heap pollution** mô tả trạng thái một generic reference/data structure không còn bảo đảm type arguments như khai báo, có thể tồn tại trước khi phát sinh lỗi.

Ví dụ cảnh báo:

~~~java
Object unknown = List.of("A");
List<String> typed = (List<String>) unknown; // Unchecked warning.
String value = typed.get(0);                 // Thành công với dữ liệu đúng.
~~~

Unchecked cast là một **đường rủi ro**, chưa đủ chứng minh danh sách thực sự có phần tử sai trong trường hợp này. Viết tests cho cả **dữ liệu hợp lệ** lẫn **dữ liệu sai** sẽ giúp phân biệt phương thức xác thực có hành vi đúng.

## 17. Test cho pipeline nhiều lớp: đặt kiểm tra ở ranh giới và nơi tiêu thụ

Một hệ thống thực tế có thể chuyển dữ liệu qua nhiều lớp:

~~~text
Nguồn bên ngoài / legacy API
       │ trả List raw / Object
       ▼
Repository hoặc adapter
       │ unchecked cast
       ▼
Service giữ List<String>
       │ gọi size(), truyền list qua nhiều methods
       ▼
Consumer / renderer
       │ String s = list.get(index)
       ▼
ClassCastException
~~~

Một bộ kiểm thử tốt nên có:

1. **Boundary test:** đầu vào List<Integer> không được âm thầm trở thành List<String>.
2. **Contract test:** adapter trả List<String> phải chứa String thực, hoặc fail sớm có chẩn đoán rõ.
3. **Mutation test:** raw aliases không được sửa dữ liệu mà API đã hứa chỉ chứa String.
4. **Consumer test:** logic đòi String không phải là chỗ duy nhất phát hiện dữ liệu bị ô nhiễm.
5. **Regression test:** sau khi sửa bug, input sai bị chặn ở điểm phù hợp và input hợp lệ vẫn được xử lý.

Ở unit tests, tạo dữ liệu sai qua raw aliases là hợp lý để tái hiện lỗ hổng. Nhưng trong production code, tránh cố ý giữ raw aliases chỉ vì test đã mô phỏng đường đó.

## 18. Cách kiểm thử với JUnit 5 nếu dự án đã sử dụng framework

Chương trình ở phần 9 không cần thư viện ngoài. Nếu dự án có **JUnit Jupiter**, có thể chuyển một trường hợp sang `assertThrows`:

~~~java
@Test
void pollutedListFailsWhenReadAsString() {
    List<String> values = new ArrayList<>(List.of("safe"));
    List raw = values;
    raw.add(42);

    assertEquals(2, values.size());

    Object value = values.get(1);
    assertEquals(42, value);

    assertThrows(ClassCastException.class, () -> {
        String text = values.get(1);
        System.out.println(text);
    });
}
~~~

Đây là **mảnh mã dành cho một lớp test JUnit 5**, không phải file Java chạy độc lập. Nó yêu cầu dependency JUnit Jupiter và các imports cần thiết:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
~~~

Điểm quan trọng không phải tên framework mà là **ranh giới của assertThrows**: chỉ bọc phép đọc typed value, sau khi test đã xác nhận raw mutation trước đó thành công.

Một assertion quá rộng:

~~~java
// assertThrows(ClassCastException.class, () -> {
//     setup();
//     insertWrongValue();
//     consumeValue();
// });
~~~

có thể tạo **false confidence**: bất kỳ bước nào trong khối ném đúng loại exception cũng làm test “pass” dù thời điểm không đúng như bug muốn tái hiện.

### 18.1. Kiểm thử negative path phải chặt về loại exception

Nếu yêu cầu API từ chối dữ liệu không đúng schema bằng IllegalArgumentException ngay ở boundary, đừng viết `assertThrows(Exception.class, ...)`. Một ClassCastException xảy ra rất muộn cũng là Exception, nên expectation quá rộng có thể che failure mode mà test đáng lẽ phải phát hiện.

Dùng loại cụ thể cùng assertions trước/sau thao tác để kiểm tra thời điểm và hậu điều kiện.

## 19. Không phụ thuộc vào thông điệp nguyên văn của ClassCastException

Thông điệp có thể khác theo JDK, classloaders, module names, proxy classes và cách bytecode được sinh:

~~~text
class java.lang.Integer cannot be cast to class java.lang.String
~~~

Đây chỉ là một dạng thông điệp minh họa. Khi test:
- Ưu tiên assert **exception class** và đúng operation.
- Nếu API yêu cầu thông điệp nghiệp vụ ổn định, assert thông điệp do **chính API tạo**.
- Tránh so khớp tuyệt đối toàn bộ JVM-generated ClassCastException message vì nó không phải contract ổn định qua môi trường.
- Có thể lưu cause/stack trace và context để debug, nhưng test logic không nên bị ràng buộc vào offset bytecode hoặc đường dẫn source.

Chương trình `HeapPollutionTest` chỉ in `ClassCastException`, `ArrayStoreException` hoặc `IllegalArgumentException` từ `getClass().getSimpleName()` để stdout ổn định.

## 20. Những lỗi thường gặp khi thiết kế bài test

### Lỗi A — test chỉ assert exception ở cuối toàn bộ workflow

Nó không phân biệt exception do cast, write, read, lambda hay bước khác. Hãy test từng operation và xác nhận các bước trước.

### Lỗi B — nghĩ rawtypes warning là exception

Warnings là diagnostics của compiler, không được JVM tự biến thành lỗi runtime. Test cần cả compile diagnostics và runtime assertions khi muốn dạy học cơ chế này.

### Lỗi C — tưởng cast sang List<String> đã validate phần tử

`(List<String>) unknown` chỉ có khả năng kiểm tra raw runtime class List, không có kiểm tra tự động tất cả String elements. Duyệt `List<?>` để validate.

### Lỗi D — dùng `new List<String>[n]` trong ví dụ runnable

Java cấm generic array creation với non-reifiable List<String>. Dùng varargs hoặc mô tả một raw array **chỉ khi muốn chủ động minh họa rủi ro**; không lén ép unchecked vào production code để lách.

### Lỗi E — cho rằng ArrayStoreException và ClassCastException xảy ra cùng một nơi

ArrayStoreException có thể xuất hiện ở **write vào reified array**. ClassCastException có thể xuất hiện ở **cast/typed read**, hoặc tại runtime-checked wrapper write. Phải xem mechanism cụ thể.

### Lỗi F — giả định `List.copyOf` tự xác minh String

`List.copyOf` không có token String để inspect generic arguments. Validator phải duyệt và kiểm tra từng element trước khi công bố type cụ thể.

### Lỗi G — đặt @SafeVarargs lên unsafe method

Annotation là lời cam kết của tác giả API, không phải một compiler proof hay runtime guard. Nếu method đưa List<Integer> vào List<String>[] backing, lời cam kết đó sai.

### Lỗi H — tắt hết warnings bằng @SuppressWarnings

Suppress rộng có thể che thêm raw aliases/unchecked casts mới. Ưu tiên loại bỏ nguyên nhân và cô lập thao tác phải tương thích legacy kèm invariant được giải thích.

### Lỗi I — chỉ test happy path

Một List<String> thật sự chứa toàn String sẽ vượt qua cast và đọc bình thường. Phải thử List<Integer>/mixed data để xác thực đường chặn sai kiểu.

### Lỗi J — chỉ nhìn tên class implementation của List

`names.getClass()` trả ArrayList (hoặc một class khác), không chứng minh type argument String. Runtime class có thể giống nhau với những List<E> khác E.

### Lỗi K — dùng `assert` của Java mà quên -ea

Các Java assert statements có thể bị tắt mặc định. Nếu mục tiêu là test harness đơn giản, dùng checks chủ động ném AssertionError như phần 9 hoặc chạy với `java -ea` có chủ đích.

### Lỗi L — bỏ qua shared mutable aliases

Một checked wrapper hoặc defensive copy chỉ có ý nghĩa nếu đường ghi không an toàn thực sự bị kiểm soát. Nếu vẫn giữ raw alias tới backing list và cho sửa trực tiếp, invariant có thể bị phá từ đường khác.

## 21. Chiến lược sửa lỗi production

Một quy trình từ test đến sửa:

1. **Tái hiện chính xác** đường tạo dữ liệu sai kiểu bằng test riêng; ghi nhận compiler warnings.
2. **Xác định nơi pollution xảy ra**, không chỉ nơi ClassCastException được ném.
3. **Thay raw types bằng parameterized types** hoặc `List<?>` nếu loại phần tử chưa biết.
4. **Không dùng unchecked cast như validation**; xác minh dữ liệu từ bên ngoài từng phần tử khi cần.
5. **Cân nhắc defensive copy** để cắt mutable alias giữa boundary và core domain.
6. **Nếu dùng generic varargs**, không ghi qua Object[] alias, không trả/làm lộ mảng backing khi không chứng minh được an toàn.
7. **Chỉ dùng @SafeVarargs** khi contract của method đã được xem xét và an toàn.
8. **Nếu cần runtime insertion checks**, dùng API như `Collections.checkedList` với token phù hợp và bảo đảm không lộ backing reference.
9. **Đặt test negative ở boundary** để sai kiểu bị báo sớm với exception hợp lý theo API, thay vì để CCE rơi ra ngẫu nhiên ở renderer.
10. **Giữ regression test cho typed read** để bảo đảm lỗi cũ không tái xuất hiện khi code legacy được chỉnh sửa.
11. **Dùng javap khi cần**, tìm compiler-inserted checkcast để hiểu vì sao stack trace trỏ đến một dòng tưởng như chỉ gọi `get`.
12. **Không thay một lỗi bằng unchecked suppression**; thông điệp compiler có thể được tắt nhưng dữ liệu vẫn sai.

### 21.1. API boundary nên nhận List<?> hay List<String>?

Nếu caller là mã typed Java được compiler kiểm tra đầy đủ và không có nguồn raw/unchecked không tin cậy, `List<String>` là hợp đồng hữu ích.

Nếu đối số đến từ deserialization, reflection, legacy raw API hoặc một object không chắc chắn, `List<?>`/`Object` có thể là kiểu đầu vào trung thực hơn; sau khi xác thực thì mới trả `List<String>`. Quyết định phụ thuộc nơi nào giữ trách nhiệm chứng minh invariant.

Đừng vô cớ làm mọi method nhận Object nếu code đã có type safety đúng; cách xử lý linh hoạt nên nằm ở **ranh giới rủi ro**, còn core code giữ generic types chặt chẽ.

## 22. Checklist review code và test

- [ ] Phân biệt rawtypes warning, unchecked warning, heap pollution và ClassCastException.
- [ ] Test xác định **thao tác ghi sai** có ném exception hay chưa.
- [ ] Test đọc dưới `Object` và đọc dưới `String` bằng **hai assertions riêng**.
- [ ] Test cast sang `List<String>` từ Object là unchecked, không xác minh phần tử.
- [ ] Với varargs generic, kiểm tra runtime component List[] và array covariance.
- [ ] Với String[], kiểm tra ArrayStoreException xuất hiện ngay ở write.
- [ ] Với Collections.checkedList, kiểm tra invalid insertion qua wrapper thất bại ngay.
- [ ] Kiểm tra liệu mutable raw alias đến backing collection còn tồn tại không.
- [ ] Tạo validated typed copy tại nơi nhận dữ liệu không tin cậy.
- [ ] Không suppress compiler warnings mà không có chứng minh an toàn.
- [ ] Dùng `javac --release 17 -Xlint:rawtypes,unchecked,varargs` để xem diagnostics.
- [ ] Dùng `javap -c -p` khi cần tìm inserted `checkcast`.
- [ ] Bọc `assertThrows`/`expect` càng sát **thao tác muốn thử** càng tốt.
- [ ] Không hard-code đầy đủ message của JVM exception nếu không phải contract ứng dụng.
- [ ] Test cả dữ liệu đúng kiểu và dữ liệu sai kiểu.
- [ ] Đảm bảo tests fail khi **không xảy ra exception** như mong đợi.
- [ ] Đánh giá thêm mutability, null, aliasing và concurrency nếu dữ liệu được chia sẻ nhiều lớp.

## 23. Câu hỏi tự kiểm tra

**1.** Vì sao `List raw = names; raw.add(42);` có thể chạy mà chưa ném ClassCastException?

**Đáp án:** Raw List không giữ type argument String trong lời gọi add, và ArrayList không có runtime check String cho element type của một List<String> thông thường. Compiler báo unchecked warning, nhưng phép ghi có thể được chấp nhận.

**2.** Nếu sau đó `Object value = names.get(1)` chạy được, danh sách đã an toàn chưa?

**Đáp án:** Chưa. Đọc như Object không chứng minh element là String. Một typed read `String value = ...` vẫn có thể fail.

**3.** Điểm JVM thường phát hiện Integer không phải String trong typed read là gì?

**Đáp án:** `checkcast java/lang/String` do compiler chèn khi cần dùng kết quả generic get như String.

**4.** Một unchecked cast `(List<String>) unknown` có luôn ném ngay không?

**Đáp án:** Không. Nếu unknown là List<Integer>, raw List check có thể qua; nhưng nếu unknown là một object không phải List, cast có thể ném ngay ở đó.

**5.** Vì sao một backing varargs `List<String>[]` có runtime component List?

**Đáp án:** Generic argument String không reifiable ở component type List<String>; compiler có thể tạo List[] khi chuẩn bị generic varargs call.

**6.** Ghi `List.of(99)` vào backing List[] qua Object[] có bị ArrayStoreException không?

**Đáp án:** Không nhất thiết; List<Integer> vẫn là một List đối với runtime component check. Lỗi có thể xuất hiện về sau khi đọc Integer như String.

**7.** Vì sao `String[]` qua Object[] alias chặn Integer ngay tại write?

**Đáp án:** String[] là reifiable array có runtime component String; JVM thực hiện array-store check và ném ArrayStoreException.

**8.** `Collections.checkedList(new ArrayList<>(),String.class)` giúp chặn gì?

**Đáp án:** Nó dùng String.class để kiểm tra runtime type của phần tử được chèn qua wrapper; raw add(Integer) qua wrapper ném ClassCastException ngay tại write.

**9.** Checked wrapper có bảo vệ được khi ai đó còn raw alias tới backing list không?

**Đáp án:** Không. Đường bypass wrapper vẫn có thể sửa backing list trực tiếp và làm hỏng dữ liệu.

**10.** Vì sao `List.copyOf` không đủ làm validator cho List<?> chưa tin cậy?

**Đáp án:** Nó sao chép elements nhưng không tự kiểm tra từng Object là String theo một generic type argument không có class token. Cần validate từng element rồi mới công bố List<String>.

**11.** Bài test chỉ viết `assertThrows(ClassCastException.class, () -> doEverything())` thiếu điều gì?

**Đáp án:** Không xác định exception phát sinh ở thao tác cụ thể nào; các lỗi từ bước khác có thể khiến test pass nhầm.

**12.** Một List<String> đã có Integer nhưng chỉ gọi `size()` có nhất thiết ném CCE không?

**Đáp án:** Không. size không cần typed element cast. Pollution có thể tồn tại lâu trước khi được phát hiện.

**13.** ClassCastException có nhất thiết là do heap pollution không?

**Đáp án:** Không. Một checked cast sai như `(String) Integer.valueOf(1)` cũng phát ClassCastException mà không có generic data structure.

**14.** Tại sao compiler warnings được xem là phần của kiểm thử dù chương trình vẫn chạy?

**Đáp án:** Chúng chỉ ra các đường không được kiểm tra đầy đủ; nếu chỉ chạy happy path thì có thể bỏ qua rủi ro tiềm ẩn. Test bao gồm cả diagnostics và runtime behavior.

**15.** Với nguồn Object từ bên ngoài, cách trả List<String> đáng tin cậy là gì?

**Đáp án:** Trước tiên xác nhận object là List<?>; duyệt từng element và kiểm tra `instanceof String`; tạo collection mới có type argument String và tránh chia sẻ raw mutable alias.

**16.** Vì sao thêm `@SafeVarargs` vào method cố tình thay `groups[0]` bằng `List.of(99)` không sửa bug?

**Đáp án:** Annotation không thêm runtime validation và không chứng minh implementation an toàn; backing List[] vẫn có thể bị heap pollution.

**17.** Kết quả `TOTAL=15` trong chương trình test chứng minh điều gì?

**Đáp án:** Tất cả 15 assertions đã qua và những exception cụ thể xuất hiện ở đúng operation được test bọc. Nó không phải chứng minh rằng mọi trường hợp heap pollution khác đều đã được loại trừ khỏi ứng dụng.

## 24. Tổng kết

Với Java Generics, **heap pollution là trạng thái dữ liệu/kiểu đã bị phá vỡ**, còn **ClassCastException là một cách lỗi được phát hiện lúc runtime cần cast về class cụ thể**. Hai sự kiện đó có thể xảy ra ở **hai thời điểm rất xa nhau**.

~~~text
Raw alias / unchecked generic conversion / generic varargs
                       │
                       ▼
            Dữ liệu sai generic type
                       │
                 Chưa chắc lỗi
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
     size(), Object read       Typed read / cast
       có thể chạy             yêu cầu String
                                    │
                                    ▼
                             ClassCastException

Ngoại lệ cần phân biệt:
String[] + Object[] alias + ghi Integer → ArrayStoreException tại write
CheckedList<String> + ghi Integer qua wrapper → ClassCastException tại write
~~~

Muốn kiểm thử đúng, phải xác nhận **thứ tự sự kiện**: compiler warning, cast/alias, mutation, safe read, typed read, và expected exception tại đúng điểm. Dùng chương trình kiểm thử tự chứa hoặc `assertThrows` sát thao tác, xem `checkcast` bằng `javap` nếu cần, và sửa nguyên nhân ở đường raw/unchecked alias hoặc boundary validation thay vì chỉ bắt ClassCastException ở nơi lỗi bộc lộ.

**Ghi nhớ:** Java Generics bảo vệ rất tốt khi toàn bộ luồng dữ liệu tuân thủ type checking. Khi thoát khỏi vùng an toàn bằng raw types, unchecked casts hay non-reifiable varargs, chương trình phải tự quản lý invariant — nếu không, lỗi có thể đến muộn và xa nguồn gây ra nó.
