# Biến cục bộ trùng tên trong khối lồng và các khai báo không hợp lệ — Java 17+

## 1. Quy tắc cốt lõi

**Phạm vi (scope)** của một biến cục bộ xác định vùng mã nơi tên của nó có thể được sử dụng. Trong Java, khi một biến cục bộ đã nằm trong phạm vi, **không được khai báo một biến cục bộ khác cùng tên ở khối lồng bên trong**. Java báo lỗi biên dịch, ngay cả khi lập trình viên muốn biến trong “che” biến ngoài.

~~~java
static void invalid() {
    int count = 10;
    {
        // int count = 20; // LỖI BIÊN DỊCH: count đã được khai báo.
        System.out.println(count); // Hợp lệ: dùng count của khối ngoài.
    }
}
~~~

Điều này khác với việc **biến cục bộ hoặc tham số che khuất trường (field) của lớp**; trường vẫn có thể được truy cập qua `this.field` hoặc `ClassName.field`.

**Phân biệt cần nhớ:** cùng tên trong hai khối **có phạm vi không chồng lấn** có thể hợp lệ; cùng tên trong hai khối **lồng nhau khi biến ngoài còn trong phạm vi** thì không.

## 2. Các trường hợp hợp lệ và không hợp lệ

| Tình huống | Hợp lệ? | Giải thích |
|---|---|---|
| `int x=1; int x=2;` trong cùng khối | **Không** | Khai báo trùng tên biến cục bộ |
| Khai báo `x` trong khối con khi `x` của khối cha đang trong phạm vi | **Không** | Java cấm khai báo lại biến cục bộ trong phạm vi chồng lấn |
| Dùng lại `x` trong hai khối ngang hàng | **Có** | Hai phạm vi tách biệt |
| Khai báo `x` sau khi khối chứa một `x` khác đã kết thúc | **Có** | Phạm vi cũ không kéo dài ra ngoài khối |
| Tham số `x`, rồi khai báo `int x` trong thân hoặc khối con của phương thức | **Không** | Trùng tên với tham số còn trong phạm vi |
| Biến cục bộ `name` cùng tên field `name` | **Có** | Biến cục bộ che khuất field |
| Tham số `name` cùng tên field `name` | **Có** | Dùng `this.name` để truy cập instance field |
| Hai vòng `for (int i=...)` tuần tự | **Có** | `i` của vòng thứ nhất hết phạm vi trước vòng kế |
| Khai báo `int i` trong thân của vòng `for (int i=...)` | **Không** | `i` vòng ngoài còn trong phạm vi |
| Lambda khai báo tham số cùng tên local đang trong phạm vi | **Không** | Tham số lambda không được khai báo trùng biến cục bộ bao quanh |

**Lưu ý thuật ngữ:** *shadowing* của một field bởi local là hợp lệ; việc khai báo lại local đang trong phạm vi ở khối con không phải một cơ chế shadowing được Java cho phép.

## 3. Hai khối độc lập được phép dùng cùng tên

~~~java
static void siblings() {
    {
        int value = 1;
        System.out.println("first=" + value);
    }

    {
        int value = 2;
        System.out.println("second=" + value);
    }

    int value = 3;
    System.out.println("after=" + value);
}
~~~

**Exact stdout khi gọi `siblings()`:**

~~~text
first=1
second=2
after=3
~~~

Mỗi `value` được khai báo khi `value` ở khối trước **đã ra khỏi phạm vi**. Không có ba biến cùng tên cùng tồn tại trong một vùng khai báo chồng lấn.

Ngược lại:

~~~java
// KHÔNG BIÊN DỊCH nếu bỏ chú thích:
static void duplicate() {
    int value = 1;
    // int value = 2; // Trùng tên trong cùng khối.
    {
        // int value = 3; // Trùng local ở khối ngoài.
    }
}
~~~

Việc **gán lại** thì hoàn toàn khác với **khai báo lại**:

~~~java
int value = 1;
value = 2; // Hợp lệ: cập nhật biến đã tồn tại.
~~~

## 4. Tham số và biến đếm `for` cũng có phạm vi

Tham số phương thức có thể được đọc trong thân và các khối con của phương thức. Không được khai báo biến local trùng tên nó ở đó:

~~~java
static void process(int total) {
    // int total = 0; // Lỗi: trùng tham số.
    {
        // int total = 5; // Cũng lỗi.
        System.out.println(total);
    }
}
~~~

Với vòng `for`:

~~~java
for (int i = 0; i < 2; i++) {
    System.out.println("loopA=" + i);
    // int i = 99; // Lỗi: i của for đang trong phạm vi.
}

for (int i = 2; i < 4; i++) {
    System.out.println("loopB=" + i);
}
~~~

**Exact stdout:**

~~~text
loopA=0
loopA=1
loopB=2
loopB=3
~~~

Tên `i` có thể được sử dụng lại vì vòng `for` thứ nhất đã kết thúc **vùng phạm vi khai báo `i`**. Nhưng nếu khai báo `int i = 10;` ở khối bao quanh cả hai vòng, việc khai báo `for (int i = ...)` bên trong sẽ bị cấm.

## 5. Field shadowing là trường hợp khác

Một local/parameter cùng tên **field** vẫn hợp lệ, vì field không phải local của khối chứa method:

~~~java
class Person {
    private String name = "FIELD";
    void print(String name) {
        System.out.println(name);      // Tham số
        System.out.println(this.name); // Field
    }
}
~~~

Trong `static` context, dùng tên lớp để chỉ field `static` bị che khuất. Điều này khác hoàn toàn với khai báo lại local/parameter trong khối lồng đang chồng phạm vi; bài về field shadowing đi sâu vào việc cập nhật đúng field.

## 6. Khai báo trùng tên khác lỗi gán chưa chắc chắn

~~~java
static int choose(boolean flag) {
    int result;
    if (flag) result = 1;
    else result = 2;
    return result; // Đã gán ở cả hai đường tới return.
}
~~~

Ở đây chỉ có **một** biến `result` và không có khai báo trùng tên. Nếu bỏ `else`, lỗi khi đọc `result` là *definite assignment*, vì nhánh `false` có thể chưa gán; đây là phép kiểm tra khác với kiểm tra khai báo trùng phạm vi.

## 7. Lambda: không khai báo tham số trùng local bao quanh

~~~java
static void lambdaExample() {
    int bonus = 3;
    java.util.function.IntUnaryOperator plusBonus =
            number -> number + bonus;

    System.out.println("lambda=" + plusBonus.applyAsInt(4));
}
~~~

**Exact stdout:**

~~~text
lambda=7
~~~

Nếu dùng `bonus -> bonus + 1` làm tham số lambda ngay tại đây, tên tham số `bonus` sẽ trùng với local `bonus` bao quanh và không hợp lệ.

Biến local được lambda **capture** phải là `final` hoặc *effectively final* (không được gán lại sau khi khởi tạo). Đây là một yêu cầu khác ngoài quy tắc trùng tên:

~~~java
// int bonus = 3;
// bonus++;
// IntUnaryOperator op = x -> x + bonus; // Không hợp lệ: bonus không effectively final.
~~~

## 8. Chương trình Java 17+ hoàn chỉnh

Lưu đúng file **`LocalScopeNameDemo.java`**:

~~~java
public final class LocalScopeNameDemo {
    private String name = "FIELD";
    private static String label = "STATIC_FIELD";

    private static void nestedBlock() {
        int count = 10;
        {
            int increment = 5;
            System.out.println("nested total=" + (count + increment));
            // int count = 20; // Không hợp lệ.
        }
        System.out.println("outer count=" + count);
    }

    private static void siblingBlocks() {
        {
            int value = 1;
            System.out.println("first=" + value);
        }
        {
            int value = 2;
            System.out.println("second=" + value);
        }
        int value = 3;
        System.out.println("after=" + value);
    }

    private static void consecutiveLoops() {
        for (int i = 0; i < 2; i++) {
            System.out.println("loopA=" + i);
        }
        for (int i = 2; i < 4; i++) {
            System.out.println("loopB=" + i);
        }
    }

    private void showFields(String name) {
        System.out.println("parameter=" + name);
        System.out.println("instance field=" + this.name);
        String label = "LOCAL";
        System.out.println("local label=" + label);
        System.out.println("static field=" + LocalScopeNameDemo.label);
    }

    private static int initialized(boolean flag) {
        int result;
        if (flag) {
            result = 1;
        } else {
            result = 2;
        }
        return result;
    }

    private static void lambdaExample() {
        int bonus = 3;
        java.util.function.IntUnaryOperator add =
                value -> value + bonus;
        System.out.println("lambda=" + add.applyAsInt(4));
    }

    public static void main(String[] args) {
        nestedBlock();
        siblingBlocks();
        consecutiveLoops();
        new LocalScopeNameDemo().showFields("PARAMETER");
        System.out.println("assigned true=" + initialized(true));
        System.out.println("assigned false=" + initialized(false));
        lambdaExample();
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 LocalScopeNameDemo.java
java -cp . LocalScopeNameDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\LocalScopeNameDemo.java
java -cp . LocalScopeNameDemo
~~~

### Exact expected stdout

~~~text
nested total=15
outer count=10
first=1
second=2
after=3
loopA=0
loopA=1
loopB=2
loopB=3
parameter=PARAMETER
instance field=FIELD
local label=LOCAL
static field=STATIC_FIELD
assigned true=1
assigned false=2
lambda=7
~~~

**Giải thích:** khối lồng đọc `count` của khối ngoài, nhưng không khai báo lại nó; ba khối không chồng lấn dùng lại tên `value`; hai vòng `for` tuần tự dùng lại `i`. Tham số `name` che khuất instance field, được phân biệt bằng `this.name`; local `label` che khuất static field, được phân biệt bằng tên lớp.

## 9. Lỗi thường gặp và bài tập

| Sai lầm | Nguyên nhân | Cách sửa |
|---|---|---|
| `int x=1;` rồi `int x=2;` | Trùng tên local cùng khối | Gán `x=2;` hoặc đổi tên |
| Khai báo `int x` ở khối trong khi local `x` ngoài còn hiệu lực | Phạm vi chồng lấn | Dùng biến cũ, hoặc chọn tên mới |
| Khai báo local trùng tham số | Tham số vẫn trong phạm vi | Đổi tên local |
| Khai báo local trùng biến đếm `for` bên trong thân `for` | `i` của vòng còn hiệu lực | Dùng chỉ số sẵn có |
| Nghĩ local trùng field luôn bị cấm | Field có thể bị local che khuất | Dùng `this.field` hoặc `ClassName.field` khi cần |
| Dùng biến sau khi ra khỏi khối khai báo | Tên hết phạm vi | Khai báo ở khối phù hợp |
| Sử dụng local chưa gán ở mọi đường | Definite assignment chưa thỏa | Gán ở tất cả đường đi |
| Lambda tham số trùng local bao quanh | Khai báo trùng tên | Đổi tên tham số lambda |
| Lambda capture local bị gán lại | Không effectively final | Không gán lại hoặc chuyển cách lưu trạng thái |

**Bài A.** Đoạn nào hợp lệ?

~~~java
{
    int n = 1;
}
{
    int n = 2;
}
~~~

**Đáp án:** hợp lệ, vì hai phạm vi riêng biệt.

**Bài B.** Vì sao đoạn này sai?

~~~java
int n = 1;
{
    // int n = 2;
}
~~~

**Đáp án:** `n` bên ngoài vẫn trong phạm vi tại khối con, nên không thể khai báo local `n` lần nữa ở đó.

**Bài C.** Với instance field `name` và tham số `name`, truy cập field ra sao? **`this.name`**.

**Bài D.** `int result;` rồi chỉ gán `result` trong `if (flag)` có dùng được sau `if` không? **Không chắc**; nếu `flag == false`, biến chưa khởi tạo. Cần gán ở nhánh `else` hoặc trước `if`.

## 10. Checklist và kết luận

- [ ] Biết phạm vi tên của biến cục bộ bắt đầu từ khai báo trong khối tương ứng.
- [ ] Không khai báo local trùng tên trong cùng khối hoặc khối con có phạm vi chồng lấn.
- [ ] Dùng lại tên trong hai khối tuần tự không chồng lấn khi hợp lý.
- [ ] Phân biệt khai báo lại với gán lại.
- [ ] Hiểu tham số và biến `for` cũng có phạm vi riêng.
- [ ] Phân biệt shadowing **field** hợp lệ với redeclaration **local** bị cấm.
- [ ] Dùng `this.field` hoặc `ClassName.field` để truy cập field bị che khuất.
- [ ] Phân biệt lỗi trùng tên với lỗi definite assignment.
- [ ] Nhớ lambda parameter không được trùng local bao quanh.
- [ ] Chạy `LocalScopeNameDemo.java` bằng Java 17+ và đối chiếu exact stdout.

**Kết luận:** Java không cho khai báo một biến cục bộ hoặc tham số mới **trùng tên local đang nằm trong phạm vi bao quanh**. Tên có thể tái sử dụng khi phạm vi trước đã kết thúc, và local/parameter có thể **che khuất field** của lớp. Xác định đúng phạm vi của từng tên sẽ tránh lỗi biên dịch và giúp chọn cách đặt tên dễ đọc.