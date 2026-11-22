# Guard clause để giảm mức lồng nhau — Java 17+

**Guard clause** (*mệnh đề bảo vệ*) là kiểm tra đặt ở **đầu một phương thức hoặc đoạn xử lý** để loại bỏ sớm những trường hợp không thể tiếp tục. Khi điều kiện loại trừ đúng, chương trình **thoát sớm** bằng `return`, `throw` hoặc, trong vòng lặp, `continue`. Phần xử lý chính vì vậy không phải nằm sâu trong nhiều lớp `if`.

~~~java
static String greet(String name) {
    if (name == null || name.isBlank()) {
        return "Tên không hợp lệ";
    }

    return "Xin chào " + name.trim();
}
~~~

Với tên không hợp lệ, phương thức trả kết quả ngay; lệnh tạo lời chào **không chạy**. Đây là một kỹ thuật tổ chức luồng điều khiển bằng các câu lệnh Java thông thường, **không phải từ khóa hoặc cú pháp mới**.

## 1. So sánh trước và sau khi dùng guard clause

### Nhiều cấp `if` lồng nhau

~~~java
static String checkNested(String name, Integer age, boolean banned) {
    if (name != null && !name.isBlank()) {
        if (age != null) {
            if (age >= 18) {
                if (!banned) {
                    return "approved:" + name.trim();
                } else {
                    return "reject:banned";
                }
            } else {
                return "reject:underage";
            }
        } else {
            return "reject:age-missing";
        }
    } else {
        return "reject:name";
    }
}
~~~

Mỗi điều kiện bổ sung đẩy đường đi thành công vào sâu hơn. Người đọc phải theo dõi nhiều dấu `{ }` và nhánh `else` mới tìm được câu xử lý chính.

### Tách các trường hợp loại trừ bằng guard

~~~java
static String checkGuarded(String name, Integer age, boolean banned) {
    if (name == null || name.isBlank()) {
        return "reject:name";
    }
    if (age == null) {
        return "reject:age-missing";
    }
    if (age < 18) {
        return "reject:underage";
    }
    if (banned) {
        return "reject:banned";
    }

    return "approved:" + name.trim();
}
~~~

Cả hai phiên bản cho **cùng kết quả** với những đầu vào minh họa ở bài, nhưng phiên bản guard làm nổi bật **đường đi thành công** ở cuối, thay vì giấu nó trong bốn cấp lồng nhau.

| Khía cạnh | `if` lồng nhau | Guard clause |
| --- | --- | --- |
| Kiểm tra đầu vào sai | Nằm ở nhiều nhánh `else` | Đọc theo thứ tự từ trên xuống |
| Phần xử lý chính | Dễ bị đẩy sâu vào trong | Ở mức thụt dòng ngoài cùng của phương thức |
| Luồng thoát | Có thể là một nhánh khác | Rõ ràng: `return` hoặc `throw` |
| Khi nên dùng | Có nhiều nhánh nghiệp vụ thực sự phải đi tiếp | Muốn loại bỏ các trường hợp không hợp lệ sớm |
| Rủi ro | Lồng sâu, dễ nhầm `else` | Quá nhiều điểm thoát nếu tổ chức kém |

**Không có quy tắc bắt buộc** mọi `if` phải biến thành guard. Mục tiêu là luồng điều khiển **dễ hiểu, đúng ngữ nghĩa**.

## 2. Chương trình Java 17+ hoàn chỉnh

Tạo tệp UTF-8 tên **`GuardClauseDemo.java`**:

~~~java
public class GuardClauseDemo {
    static String checkNested(String name, Integer age, boolean banned) {
        if (name != null && !name.isBlank()) {
            if (age != null) {
                if (age >= 18) {
                    if (!banned) {
                        return "approved:" + name.trim();
                    } else {
                        return "reject:banned";
                    }
                } else {
                    return "reject:underage";
                }
            } else {
                return "reject:age-missing";
            }
        } else {
            return "reject:name";
        }
    }

    static String checkGuarded(String name, Integer age, boolean banned) {
        if (name == null || name.isBlank()) {
            return "reject:name";
        }
        if (age == null) {
            return "reject:age-missing";
        }
        if (age < 18) {
            return "reject:underage";
        }
        if (banned) {
            return "reject:banned";
        }
        return "approved:" + name.trim();
    }

    static String trace(String name, Integer age, boolean banned) {
        System.out.println("check=name");
        if (name == null || name.isBlank()) {
            return "reject:name";
        }

        System.out.println("check=age");
        if (age == null || age < 18) {
            return "reject:age";
        }

        System.out.println("check=banned");
        if (banned) {
            return "reject:banned";
        }

        System.out.println("process=main");
        return "approved:" + name.trim();
    }

    static int averagePerPerson(int total, int people) {
        if (people <= 0) {
            throw new IllegalArgumentException("people must be positive");
        }
        if (total < 0) {
            throw new IllegalArgumentException("total must be non-negative");
        }
        return total / people;
    }

    static void printPositive(int[] numbers) {
        for (int number : numbers) {
            if (number <= 0) {
                continue;
            }
            System.out.println("positive=" + number);
        }
    }

    static void logIfPresent(String value) {
        if (value == null || value.isBlank()) {
            return;
        }
        System.out.println("log=" + value.trim());
    }

    public static void main(String[] args) {
        String[] names = {"An", null, "   ", "Binh", "Chi", "Dung", " Hoa "};
        Integer[] ages = {20, 20, 22, null, 17, 20, 21};
        boolean[] banned = {false, false, false, false, false, true, false};

        System.out.println("== nested vs guarded ==");
        for (int i = 0; i < names.length; i++) {
            String nested = checkNested(names[i], ages[i], banned[i]);
            String guarded = checkGuarded(names[i], ages[i], banned[i]);
            System.out.println("case" + (i + 1) + "=" + guarded
                    + ",same=" + nested.equals(guarded));
        }

        System.out.println("== early exit ==");
        System.out.println("invalid=" + trace(null, null, false));
        System.out.println("valid=" + trace("Lan", 25, false));

        System.out.println("== guard with throw ==");
        System.out.println("average=" + averagePerPerson(12, 3));
        try {
            averagePerPerson(12, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalidPeople=" + ex.getMessage());
        }
        try {
            averagePerPerson(-1, 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalidTotal=" + ex.getMessage());
        }

        System.out.println("== continue in loop ==");
        printPositive(new int[] {-2, 0, 3, 5});

        System.out.println("== void guard ==");
        logIfPresent(null);
        logIfPresent("  OK  ");
        System.out.println("done");
    }
}
~~~

Yêu cầu **JDK 17 trở lên**. Tại thư mục chứa tệp, sử dụng PowerShell trên Windows hoặc Bash trên Linux/macOS:

~~~bash
java -version
javac -version
javac -encoding UTF-8 GuardClauseDemo.java
java GuardClauseDemo
~~~

**Exact expected stdout** của riêng lệnh `java GuardClauseDemo`:

~~~text
== nested vs guarded ==
case1=approved:An,same=true
case2=reject:name,same=true
case3=reject:name,same=true
case4=reject:age-missing,same=true
case5=reject:underage,same=true
case6=reject:banned,same=true
case7=approved:Hoa,same=true
== early exit ==
check=name
invalid=reject:name
check=name
check=age
check=banned
process=main
valid=approved:Lan
== guard with throw ==
average=4
invalidPeople=people must be positive
invalidTotal=total must be non-negative
== continue in loop ==
positive=3
positive=5
== void guard ==
log=OK
done
~~~

`java -version` và `javac -version` có đầu ra tùy máy, không nằm trong khối stdout cố định. Mọi phương thức được sử dụng trong chương trình đều đã được định nghĩa trong cùng một lớp.

## 3. Luồng chạy của guard clause

Chương trình `trace` in từng lần kiểm tra. Với đầu vào `trace(null, null, false)`, stdout chỉ có `check=name` rồi `invalid=reject:name`. Các lần kiểm tra tuổi và trạng thái bị chặn **không diễn ra**.

Với `trace("Lan", 25, false)`, mọi guard đều vượt qua; chương trình đến phần `process=main` và trả giá trị thành công.

~~~mermaid
flowchart TD
    A["Bắt đầu phương thức"] --> B{"Tên không hợp lệ?"}
    B -- "Có" --> R1["return reject:name"]
    B -- "Không" --> C{"Tuổi thiếu hoặc quá nhỏ?"}
    C -- "Có" --> R2["return reject:age"]
    C -- "Không" --> D{"Bị chặn?"}
    D -- "Có" --> R3["return reject:banned"]
    D -- "Không" --> E["Xử lý chính"]
    E --> F["return approved"]
~~~

**Quan trọng:** `return` rời khỏi **toàn bộ phương thức hiện tại**, không chỉ rời khỏi khối `if`. Mọi câu lệnh nằm sau `return` trên đường chạy đó đều không được thực thi.

## 4. Chọn `return`, `throw` hay `continue`

Guard clause là cách tổ chức các **điểm thoát sớm**. Điểm thoát thích hợp phụ thuộc vào việc đầu vào sai là một trường hợp bình thường hay một lỗi cần báo cho bên gọi.

| Câu lệnh | Phạm vi thoát | Dùng khi |
| --- | --- | --- |
| `return value;` | Kết thúc phương thức có giá trị trả về | Một trường hợp hợp lệ được giải quyết sớm bằng kết quả |
| `return;` | Kết thúc phương thức `void` | Không có gì cần xử lý tiếp |
| `throw new ...;` | Kết thúc luồng bình thường bằng ngoại lệ | Đầu vào vi phạm hợp đồng và bên gọi cần được báo lỗi |
| `continue;` | Bỏ phần còn lại của lần lặp, sang lần kế tiếp | Loại một phần tử khỏi xử lý trong vòng lặp |
| `break;` | Kết thúc vòng lặp hoặc `switch` chứa nó | Không cần tiếp tục lặp |

### `return` trong phương thức `void`

~~~java
static void logIfPresent(String text) {
    if (text == null || text.isBlank()) {
        return;
    }
    System.out.println(text.trim());
}
~~~

`return;` không mang giá trị vì phương thức có kiểu trả về `void`.

### `throw` để báo vi phạm điều kiện đầu vào

~~~java
static int divide(int total, int divisor) {
    if (divisor == 0) {
        throw new IllegalArgumentException("divisor must not be zero");
    }
    return total / divisor;
}
~~~

Nếu `divisor` bằng 0, phương thức ném ngoại lệ **trước khi chia**, không chỉ trả một giá trị mặc định có thể che giấu lỗi.

### `continue` để tránh lồng `if` trong vòng lặp

~~~java
for (int number : numbers) {
    if (number <= 0) {
        continue;
    }
    process(number);
}
~~~

Khi `number <= 0`, `process(number)` bị bỏ qua **chỉ trong lần lặp đó**. `continue` **không** kết thúc phương thức bao quanh. `process` ở ví dụ này là tên mô tả một thao tác thực tế; chương trình runnable dùng `System.out.println` để minh họa mà không cần phương thức ngoài.

**Đừng nhầm `return` với `continue`:** dùng `return` trong vòng lặp sẽ kết thúc luôn phương thức; dùng `continue` chỉ bỏ qua phần xử lý còn lại của lần lặp hiện tại.

## 5. Thứ tự guard ảnh hưởng đến an toàn và kết quả

### Kiểm tra `null` trước khi sử dụng dữ liệu

~~~java
static boolean isAdult(Integer age) {
    if (age == null) {
        return false;
    }
    return age >= 18; // Unbox an toàn sau guard.
}
~~~

Nếu viết `if (age < 18)` trước khi kiểm tra `age == null`, Java có thể ném `NullPointerException` vì phải unbox `Integer` null.

Có thể kết hợp bằng điều kiện ngắn mạch:

~~~java
if (name == null || name.isBlank()) {
    return "reject:name";
}
~~~

`||` không gọi `name.isBlank()` nếu `name == null` đã true. Nếu dùng `|` thay `||`, cả hai vế được đánh giá và lời gọi trên null có thể ném ngoại lệ.

### Kiểm tra miền đầu vào trước khi thực hiện phép tính

~~~java
if (people <= 0) {
    throw new IllegalArgumentException("people must be positive");
}
int average = total / people;
~~~

Kiểm tra này không chỉ tránh phép chia cho 0 mà còn thực thi quy định nghiệp vụ “số người phải dương”.

### Thứ tự quyết định thông báo lỗi

~~~java
if (name == null || name.isBlank()) {
    return "reject:name";
}
if (age == null) {
    return "reject:age-missing";
}
~~~

Nếu cả hai đầu vào đều sai, guard **đầu tiên** quyết định giá trị được trả về. Khi nhiều điều kiện cùng có thể sai, hãy chọn thứ tự kiểm tra có chủ đích và giữ nguyên nếu đang refactor mã có hành vi quan sát được.

**Guard clause không tự động loại bỏ tác dụng phụ** của biểu thức điều kiện: nếu điều kiện gọi phương thức có thay đổi trạng thái, việc sắp xếp lại thứ tự guard có thể thay đổi hành vi.

## 6. Guard clause và `if/else`: nên chọn phong cách nào?

**Guard phù hợp** khi có một đường đi chính và một số điều kiện khiến xử lý phải dừng sớm:

~~~java
static String describe(String text) {
    if (text == null) {
        return "missing";
    }
    if (text.isBlank()) {
        return "empty";
    }
    return "text:" + text.trim();
}
~~~

**`if/else` phù hợp** khi cả hai nhánh đều là hành vi nghiệp vụ bình thường và có trọng lượng tương đương:

~~~java
if (isMorning) {
    serveBreakfast();
} else {
    serveDinner();
}
~~~

Hai lời gọi `serveBreakfast`/`serveDinner` minh họa cấu trúc nhánh, không thuộc chương trình runnable ở mục 2. Không cần ép một lựa chọn hai nhánh cân bằng thành nhiều guard không tự nhiên.

**Các điểm cân nhắc:**

- Giữ điều kiện guard **đơn giản, có tên rõ ràng**, ưu tiên trả sớm khi không thể tiếp tục.
- Nếu guard liên tục lặp lại ở nhiều nơi, cân nhắc một phương thức xác thực có hợp đồng rõ ràng.
- Không cố gom mọi điều kiện vào một câu `if` dài nếu các trường hợp lỗi cần thông báo riêng.
- Không dùng `return null` hoặc giá trị mặc định nếu nó khiến lỗi đầu vào nghiêm trọng trở nên khó phát hiện; cân nhắc `throw` hoặc kiểu kết quả phù hợp.
- Không đặt quá nhiều điểm thoát khiến việc theo dõi **tài nguyên và thay đổi trạng thái** trở nên khó hiểu.

## 7. Cleanup và tài nguyên khi thoát sớm

Một `return` sớm có thể bỏ qua các câu lệnh ở phía sau. Vì vậy phải tính đến thao tác dọn dẹp:

~~~java
static void example() {
    // Nếu đã mở tài nguyên, không được chỉ dựa vào một câu
    // lệnh close() nằm sau mọi đường return.
}
~~~

Với tài nguyên implements `AutoCloseable`, nên dùng **try-with-resources** để bảo đảm gọi `close()` khi rời khối, kể cả thoát bằng `return` hoặc `throw`:

~~~java
static String firstLine(java.io.BufferedReader reader)
        throws java.io.IOException {
    try (reader) {
        String line = reader.readLine();
        if (line == null) {
            return "empty";
        }
        return line;
    }
}
~~~

Ví dụ nhận một `BufferedReader` và chủ động **nhận quyền đóng reader** trong khối try. Không dùng mẫu này nếu hợp đồng yêu cầu bên gọi tiếp tục sở hữu và sử dụng reader sau lời gọi. Java cũng thực hiện khối `finally` khi rời `try` bằng `return` theo luồng thông thường; hãy tránh viết `return` trong `finally` vì có thể che giấu kết quả hoặc ngoại lệ.

## 8. Lỗi thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Guard clause là cú pháp riêng của Java.” | Chỉ là mẫu dùng `if` với điểm thoát sớm |
| “`return` chỉ thoát khỏi khối `if`.” | `return` kết thúc **phương thức** hiện tại |
| “`continue` và `return` giống nhau trong vòng lặp.” | `continue` bỏ qua một lần lặp; `return` rời phương thức |
| “Cứ đổi mọi `else` thành `return` là tốt.” | Cần giữ ngữ nghĩa và tính dễ đọc |
| “Có thể kiểm tra `age < 18` trước khi biết `age != null`.” | Có thể gây unboxing null |
| “Thứ tự các guard không quan trọng.” | Guard đầu tiên quyết định lỗi, tác dụng phụ và đường chạy |
| “`throw` và `return false` tương đương.” | Một bên là ngoại lệ, một bên là kết quả bình thường |
| “Thoát sớm luôn bỏ qua dọn dẹp `try-with-resources`.” | Tài nguyên vẫn được đóng khi rời khối theo cơ chế Java |
| “Guard luôn phải ở dòng đầu tiên.” | Đặt trước đoạn xử lý phụ thuộc vào tiền điều kiện; có thể cần khởi tạo hợp lý trước đó |

## 9. Bài tập tự kiểm tra

1. `String s = null; if (s == null) return;` có gọi `s.isBlank()` ở lệnh sau không?  
   *Đáp án:* Không; phương thức đã kết thúc.
2. Vì sao `if (age == null) return false;` hữu ích trước `age >= 18` khi `age` là `Integer`?  
   *Đáp án:* Tránh unboxing null gây `NullPointerException`.
3. Khi kiểm tra `people <= 0` và đây là lỗi đầu vào, nên làm gì?  
   *Đáp án:* Thường `throw new IllegalArgumentException(...)` nếu hợp đồng phương thức yêu cầu số người dương.
4. Trong vòng lặp, muốn bỏ qua phần tử âm nhưng vẫn tiếp tục phần tử sau thì chọn câu lệnh nào?  
   *Đáp án:* `continue`.
5. Trong vòng lặp, dùng `return` thay `continue` thì điều gì thay đổi?  
   *Đáp án:* Kết thúc toàn bộ phương thức, không xử lý phần tử sau.
6. Nếu `name` null và `age` null, phương thức `checkGuarded` báo lỗi gì?  
   *Đáp án:* `reject:name` vì guard đó đứng trước.
7. Hai phiên bản lồng nhau và dùng guard có nhất thiết luôn tương đương không?  
   *Đáp án:* Không; cần giữ thứ tự đánh giá, tác dụng phụ, kết quả và ngoại lệ.
8. Khi phương thức mở tài nguyên trước các guard, nên quản lý việc đóng tài nguyên bằng gì?  
   *Đáp án:* Ví dụ `try-with-resources` (khi phương thức chịu trách nhiệm đóng tài nguyên).

## Checklist

- [ ] Hiểu guard clause là một câu `if` để **thoát sớm khi không thể tiếp tục**.
- [ ] Dùng `return` cho kết quả/điều kiện kết thúc bình thường, `throw` cho lỗi hợp đồng.
- [ ] Dùng `continue` để bỏ qua phần tử trong vòng lặp, không nhầm với `return`.
- [ ] Kiểm tra `null` và miền giá trị trước khi dùng dữ liệu.
- [ ] Giữ **đường xử lý chính ít lồng nhau** và dễ đọc.
- [ ] Bảo toàn thứ tự kiểm tra, thông báo lỗi và tác dụng phụ khi refactor.
- [ ] Biết khi nào một `if/else` cân bằng phù hợp hơn guard.
- [ ] Không quên dọn dẹp tài nguyên khi phương thức có nhiều đường thoát.

**Kết luận:** Guard clause không thay đổi khả năng rẽ nhánh của Java; nó giúp **diễn đạt các điều kiện dừng một cách sớm và rõ**, từ đó giảm mức lồng `if` cho đường đi chính. Hãy dùng nó có chủ đích và giữ nguyên hành vi cần thiết khi chuyển từ mã lồng nhau.
