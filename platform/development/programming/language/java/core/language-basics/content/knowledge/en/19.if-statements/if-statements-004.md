# `else` gắn với `if` gần nhất chưa có `else` — Java 17+

Trong Java, nếu nhiều câu lệnh `if` **lồng nhau mà không có ngoặc nhọn xác định rõ khối**, một `else` sẽ thuộc về **`if` gần nhất ở trước nó mà chưa có `else` tương ứng**. Quy tắc này thường được gọi là **dangling else** (*else lơ lửng*).

~~~java
boolean outer = true;
boolean inner = false;

if (outer)
    if (inner)
        System.out.println("A");
    else
        System.out.println("B");
~~~

Kết quả là **`B`**, vì `else` gắn với **`if (inner)`**, không phải `if (outer)`. **Thụt đầu dòng không quyết định phạm vi câu lệnh trong Java**; cấu trúc cú pháp và dấu `{ }` mới quyết định.

Nếu `outer` là `false`, chương trình bỏ qua toàn bộ câu lệnh `if (inner) ... else ...`, vì đó là phần thân của `if (outer)`. Lúc ấy **không có dòng A/B nào được in**.

## 1. Quy tắc gắn `else` chính xác

Với đoạn sau không có ngoặc nhọn:

~~~java
if (outer)
    if (inner)
        actionA();
    else
        actionB();
~~~

Java hiểu tương đương:

~~~java
if (outer) {
    if (inner) {
        actionA();
    } else {
        actionB();
    }
}
~~~

Hai phương thức `actionA()`, `actionB()` ở hai đoạn trên chỉ là tên minh họa cú pháp; chương trình runnable ở phần tiếp theo tự định nghĩa đầy đủ các phương thức của nó.

### Bảng kết quả

| `outer` | `inner` | Hành vi của đoạn không có ngoặc |
| --- | --- | --- |
| false | false | Không gọi `actionA` hay `actionB` |
| false | true | Không gọi `actionA` hay `actionB` |
| true | false | Gọi `actionB` — `else` của `inner` |
| true | true | Gọi `actionA` |

**Không được** tự diễn giải `else` thành “nhánh ngược lại của điều kiện đầu tiên”. Khi có hai `if` lồng nhau, nó thường thuộc về `if` **bên trong** nếu `if` đó chưa có `else`.

## 2. Chương trình Java 17+ chạy độc lập

Tạo file UTF-8 tên **`DanglingElseDemo.java`**:

~~~java
public class DanglingElseDemo {
    static boolean test(String label, boolean value) {
        System.out.println("check=" + label);
        return value;
    }

    static void withoutBraces(boolean outer, boolean inner) {
        System.out.println("input=" + outer + "," + inner);

        if (outer)
            if (inner)
                System.out.println("branch=inner-true");
            else
                System.out.println("branch=inner-false");

        System.out.println("after");
    }

    static void withBraces(boolean outer, boolean inner) {
        if (outer) {
            if (inner) {
                System.out.println("braced=inner-true");
            } else {
                System.out.println("braced=inner-false");
            }
        } else {
            System.out.println("braced=outer-false");
        }
    }

    static void withTwoElses(boolean outer, boolean inner) {
        if (outer)
            if (inner)
                System.out.println("two=inner-true");
            else
                System.out.println("two=inner-false");
        else
            System.out.println("two=outer-false");
    }

    public static void main(String[] args) {
        System.out.println("== no braces ==");
        withoutBraces(false, false);
        withoutBraces(false, true);
        withoutBraces(true, false);
        withoutBraces(true, true);

        System.out.println("== explicit braces ==");
        withBraces(false, false);
        withBraces(true, false);
        withBraces(true, true);

        System.out.println("== two else keywords ==");
        withTwoElses(false, true);
        withTwoElses(true, false);
        withTwoElses(true, true);

        System.out.println("== skipped inner condition ==");
        if (test("outer", false))
            if (test("inner-skipped", true))
                System.out.println("unexpected=inner-true");
            else
                System.out.println("unexpected=inner-false");
        System.out.println("after-skipped");

        System.out.println("== else-if chain ==");
        int score = 85;
        if (score >= 90) {
            System.out.println("grade=A");
        } else if (score >= 75) {
            System.out.println("grade=B");
        } else {
            System.out.println("grade=C");
        }

        System.out.println("== independent if ==");
        boolean first = true;
        boolean second = true;
        if (first) {
            System.out.println("independent=first");
        }
        if (second) {
            System.out.println("independent=second");
        }

        System.out.println("== chained instead ==");
        if (first) {
            System.out.println("chained=first");
        } else if (second) {
            System.out.println("chained=second");
        }

        System.out.println("done");
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa file; sử dụng **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 DanglingElseDemo.java
java DanglingElseDemo
~~~

**Exact expected stdout** của riêng lệnh `java DanglingElseDemo`:

~~~text
== no braces ==
input=false,false
after
input=false,true
after
input=true,false
branch=inner-false
after
input=true,true
branch=inner-true
after
== explicit braces ==
braced=outer-false
braced=inner-false
braced=inner-true
== two else keywords ==
two=outer-false
two=inner-false
two=inner-true
== skipped inner condition ==
check=outer
after-skipped
== else-if chain ==
grade=B
== independent if ==
independent=first
independent=second
== chained instead ==
chained=first
done
~~~

Lệnh `java -version` và `javac -version` hiển thị phiên bản cài trên từng máy, nên không thuộc expected stdout cố định. Ví dụ này chỉ dùng Java chuẩn.

## 3. Dùng ngoặc nhọn để gắn `else` với `if` ngoài

Nếu muốn `else` chạy khi `outer` false thì **phải đóng phần thân của `if (outer)` trước `else`**:

~~~java
if (outer) {
    if (inner) {
        System.out.println("inner is true");
    }
} else {
    System.out.println("outer is false");
}
~~~

Trong trường hợp này, `else` **thuộc `if (outer)`**, vì `if (inner)` đã nằm trong khối ngoặc của `outer`, và khối đó kết thúc trước `else`.

So sánh trực tiếp:

| Cách viết | `else` gắn với | Khi `outer=false` |
| --- | --- | --- |
| `if (outer) if (inner) A; else B;` | `if (inner)` | Không chạy A/B |
| `if (outer) { if (inner) A; } else B;` | `if (outer)` | Chạy B |
| `if (outer) { if (inner) A; else B; }` | `if (inner)` | Không chạy A/B |

`A;` và `B;` trong bảng là ký hiệu cho một câu lệnh hợp lệ, không phải các biến có sẵn của Java. Cần thay chúng bằng câu lệnh thực tế khi sao chép để chạy.

**Nguyên tắc:** Viết dấu ngoặc nhọn cho từng nhánh ngay cả khi chỉ có một câu lệnh. Việc này khiến người đọc và trình biên dịch hiểu cùng một cấu trúc, tránh lỗi khi thêm mã sau này.

## 4. Nếu có hai `else` thì sao?

Có thể có một `else` cho `if` bên trong **và** một `else` cho `if` bên ngoài:

~~~java
if (outer)
    if (inner)
        System.out.println("inner=true");
    else
        System.out.println("inner=false");
else
    System.out.println("outer=false");
~~~

Cách viết này hợp lệ. `else` thứ nhất thuộc `if (inner)`; `else` thứ hai thuộc `if (outer)`. Nhưng khi có nhiều mức lồng, cách không ngoặc dễ làm người đọc nhầm; nên viết lại:

~~~java
if (outer) {
    if (inner) {
        System.out.println("inner=true");
    } else {
        System.out.println("inner=false");
    }
} else {
    System.out.println("outer=false");
}
~~~

| `outer` | `inner` | Nhánh được chọn |
| --- | --- | --- |
| false | bất kỳ | `outer=false` |
| true | false | `inner=false` |
| true | true | `inner=true` |

Đây là **một cây quyết định lồng nhau** chứ không phải ba điều kiện độc lập chạy liên tục.

## 5. `else if` là một `else` theo sau bởi `if`

Java không có từ khóa riêng tên `elseif`. Cú pháp:

~~~java
if (score >= 90) {
    System.out.println("A");
} else if (score >= 75) {
    System.out.println("B");
} else {
    System.out.println("C");
}
~~~

Có thể hiểu cấu trúc như:

~~~java
if (score >= 90) {
    System.out.println("A");
} else {
    if (score >= 75) {
        System.out.println("B");
    } else {
        System.out.println("C");
    }
}
~~~

Điều này giải thích vì sao `else if` thực chất kết hợp `else` với một câu `if` khác. Với chuỗi này, các điều kiện được đánh giá từ trên xuống; gặp nhánh true đầu tiên thì những nhánh sau bị bỏ qua.

**Khác `if` độc lập:** Hai câu `if` đặt liên tiếp có thể cùng chạy. Một chuỗi `if / else if / else` sẽ chỉ chạy tối đa một nhánh trong một lần đi qua chuỗi, nếu điều kiện không ném ngoại lệ.

## 6. Thụt đầu dòng không thay thế cú pháp

Đây là ví dụ dễ gây hiểu nhầm:

~~~java
boolean outer = false;
boolean inner = false;

if (outer)
    if (inner)
        System.out.println("A");
else
    System.out.println("B");
~~~

Mặc dù `else` trông giống thụt dòng cùng cấp với `if (outer)`, nó vẫn **thuộc `if (inner)`**. Khi `outer` false, không in A hoặc B. Thụt đầu dòng chỉ là hình thức trình bày mã nguồn; Java không dựa vào số khoảng trắng để ghép `else`.

Hãy sửa thành cấu trúc có ngoặc:

~~~java
if (outer) {
    if (inner) {
        System.out.println("A");
    }
} else {
    System.out.println("B");
}
~~~

Bây giờ `B` được in khi `outer` false. Hai đoạn **không tương đương** dù có thể được trình bày với thụt đầu dòng khá giống nhau.

## 7. `else` gần nhất chưa có `else` và những giới hạn cú pháp

Quy tắc “gần nhất” áp dụng cho `if` chưa có `else` trong **cấu trúc câu lệnh hợp lệ**; nó **không có nghĩa** có thể nối `else` vào bất kỳ câu `if` nào xuất hiện trước đó dù đã đóng khối hoặc tách ra bằng câu lệnh khác.

Ví dụ:

~~~java
int n = 2;

if (n > 0) {
    System.out.println("positive");
}
// else phải đặt ngay sau câu if ở trên nếu muốn tạo nhánh của nó.

System.out.println("between");
// else { System.out.println("non-positive"); } // Lỗi biên dịch.
~~~

Câu `else` không thể đứng riêng sau `System.out.println("between")` vì không có một câu `if` hợp lệ tương ứng tại vị trí cú pháp đó.

Một bẫy khác là dấu chấm phẩy ngay sau điều kiện:

~~~java
boolean ready = true;

if (ready); // Đây là if có thân là câu lệnh rỗng.
{
    System.out.println("always");
}
~~~

Khối có `System.out.println("always")` là **khối độc lập**, không phải phần thân của `if`. Vì thế hãy tránh thêm `;` sau `if (...)` và luôn xem lại vị trí đóng mở ngoặc.

## 8. Khi nào cần quan tâm thứ tự đánh giá điều kiện?

Xét:

~~~java
if (outer)
    if (inner)
        doWork();
    else
        doFallback();
~~~

Nếu `outer` false, biểu thức `inner` **không được đánh giá**, `doWork()` và `doFallback()` đều không chạy.

Điều này đáng chú ý nếu `inner` là lời gọi phương thức có log, thay đổi biến hoặc có thể ném exception. Ví dụ trong chương trình `DanglingElseDemo`:

~~~java
if (test("outer", false))
    if (test("inner-skipped", true))
        System.out.println("unexpected=inner-true");
    else
        System.out.println("unexpected=inner-false");
~~~

Chỉ xuất hiện `check=outer`, không có `check=inner-skipped`. Không phải Java “quên” đánh giá điều kiện trong; đó là quy tắc **điều khiển luồng của `if` ngoài**.

Nên tránh dựa vào tác dụng phụ ẩn trong điều kiện để thực hiện thao tác bắt buộc; hãy tách thao tác đó thành câu lệnh rõ ràng nếu nó phải xảy ra dù nhánh nào được chọn.

## 9. Những lỗi thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`else` gắn với `if` có cùng mức thụt dòng.” | Gắn với `if` gần nhất chưa có `else` theo **cú pháp** |
| “`else` luôn thuộc `if` ngoài cùng.” | Sai khi có `if` bên trong chưa có `else` |
| “Nếu `outer` false, `else` của `inner` vẫn chạy.” | Không; toàn bộ `if (inner)...else...` bị bỏ qua |
| “Thêm ngoặc nhọn chỉ để đẹp.” | Có thể **thay đổi quan hệ gắn `else`** và hành vi |
| “`else if` là một từ khóa riêng.” | Là `else` theo sau bởi câu `if` |
| “Hai `if` liên tiếp giống chuỗi `else if`.” | Hai `if` độc lập có thể cùng chạy |
| “Có thể đặt một `else` sau một câu lệnh bất kỳ.” | `else` phải theo đúng cấu trúc `if` |
| “Thêm `;` ngay sau `if (...)` vô hại.” | Tạo thân `if` rỗng, dễ làm mã chạy khác ý định |
| “Một `else` có thể thuộc hai `if` cùng lúc.” | Mỗi `else` chỉ thuộc **một** `if` hợp lệ |

## 10. Bài tập tự kiểm tra

1. Với `outer=true`, `inner=false` và đoạn `if (outer) if (inner) A; else B;`, câu lệnh nào được chạy?  
   *Đáp án:* **B**, thuộc `else` của `inner`.
2. Với `outer=false`, `inner=false` và cùng đoạn trên, có chạy `B` không?  
   *Đáp án:* **Không**; toàn bộ câu `if` bên trong bị bỏ qua.
3. Thụt `else` về cùng mức với `if (outer)` có đổi cách Java ghép `else` không?  
   *Đáp án:* **Không**.
4. Muốn `else` thuộc `if (outer)`, cách chắc chắn nhất là gì?  
   *Đáp án:* Đặt `{ }` quanh phần thân của `if (outer)`, đóng khối trước `else`.
5. Đoạn lồng có hai `else`, `else` đầu gắn với câu `if` nào?  
   *Đáp án:* `if` bên trong chưa có `else`; `else` tiếp theo thuộc `if` ngoài.
6. `else if` có được xem như một từ khóa riêng trong Java không?  
   *Đáp án:* Không; là `else` + một câu `if`.
7. Vì sao đoạn `if (outer) if (inner) A; else B;` không gọi phép kiểm tra `inner` khi `outer=false`?  
   *Đáp án:* Thân `if (outer)` đã bị bỏ qua.
8. `if (ready);` gây vấn đề gì?  
   *Đáp án:* `if` có thân rỗng; câu lệnh hoặc khối tiếp theo không được bảo vệ bởi điều kiện.

## Checklist

- [ ] Hiểu `else` gắn với **`if` gần nhất chưa có `else`** trong cấu trúc hợp lệ.
- [ ] Nhận biết `dangling else` khi viết `if` lồng nhau không ngoặc.
- [ ] Phân biệt `else` của `if` trong với `else` của `if` ngoài.
- [ ] Biết thụt đầu dòng **không quyết định** liên kết cú pháp.
- [ ] Luôn ưu tiên `{ }` để thể hiện rõ các nhánh.
- [ ] Hiểu `else if` là `else` tiếp theo bởi một câu `if`.
- [ ] Phân biệt chuỗi `else if` với nhiều câu `if` độc lập.
- [ ] Không vô tình tạo thân `if` rỗng bằng dấu `;`.

**Kết luận:** Quy tắc **dangling else** của Java đơn giản nhưng dễ gây lỗi: **`else` thuộc `if` gần nhất chưa có `else`**, bất kể cách thụt đầu dòng. Dùng ngoặc nhọn nhất quán để làm rõ ý định, tránh thay đổi hành vi khi thêm hoặc chỉnh sửa các nhánh.
