# Lỗi lệch một đơn vị tại biên vòng lặp — Java 17+

**Lỗi lệch một đơn vị** (*off-by-one error*) xảy ra khi vòng lặp chạy **thiếu một lượt** hoặc **thừa một lượt** so với yêu cầu. Lỗi thường nằm ở giá trị bắt đầu, điều kiện `<`/`<=`, bước cập nhật hoặc cách hiểu giới hạn cuối có được tính vào hay không.

~~~java
int[] numbers = {10, 20, 30};

for (int i = 0; i < numbers.length; i++) {
    System.out.println(numbers[i]); // 10, 20, 30.
}
~~~

Trong Java, mảng dài `n` có chỉ số hợp lệ từ **`0` đến `n - 1`**. Giá trị `n` là **biên kết thúc không bao gồm**; không phải chỉ số phần tử cuối.

## 1. Phân biệt biên đóng và biên mở

| Mục tiêu | Cách viết đúng | Số lượt khi miền hợp lệ |
| --- | --- | --- |
| Duyệt mảng độ dài `n` | `for (int i = 0; i < n; i++)` | `n` |
| Duyệt từ `0` đến `n` **bao gồm `n`** | `for (int i = 0; i <= n; i++)` | `n + 1` |
| Duyệt chỉ số `start` tới **trước `end`** | `for (int i = start; i < end; i++)` | `end - start` nếu `start <= end` |
| Duyệt từ `start` tới `end` **bao gồm `end`** | `for (int i = start; i <= end; i++)` | `end - start + 1` nếu `start <= end` |
| Duyệt mảng theo chiều ngược | `for (int i = a.length - 1; i >= 0; i--)` | `a.length` |

Ví dụ bắt đầu ở 1, kết thúc ở 3:

~~~text
[1, 3)  → 1, 2       (2 giá trị, không bao gồm 3)
[1, 3]  → 1, 2, 3    (3 giá trị, bao gồm 3)
~~~

Ký hiệu `[start, end)` là **đoạn nửa mở**, rất hữu ích khi xử lý chỉ số mảng. `[start, end]` là đoạn đóng; hãy ghi rõ kiểu biên trong tên biến hoặc hợp đồng phương thức.

**Cần chú ý:** các công thức số lượt trên giả định bước tăng là 1, thứ tự biên hợp lệ và không có `break`/`return`. Nếu có bước tăng khác, giảm dần hoặc kiểu số nguyên bị tràn, phải phân tích lại.

## 2. Chương trình Java 17+ tự chứa và chạy được

Tạo tệp UTF-8 **`OffByOneDemo.java`**:

~~~java
public class OffByOneDemo {
    static int sumFirst(int[] values, int count) {
        if (count < 0 || count > values.length) {
            throw new IllegalArgumentException("invalid count");
        }
        int sum = 0;
        for (int i = 0; i < count; i++) {
            sum += values[i];
        }
        return sum;
    }

    static int sumRange(int[] values, int start, int endExclusive) {
        if (start < 0 || endExclusive < start
                || endExclusive > values.length) {
            throw new IllegalArgumentException("invalid range");
        }
        int sum = 0;
        for (int i = start; i < endExclusive; i++) {
            sum += values[i];
        }
        return sum;
    }

    public static void main(String[] args) {
        int[] values = {10, 20, 30};
        System.out.println("== array indices ==");
        System.out.println("length=" + values.length);
        for (int i = 0; i < values.length; i++) {
            System.out.println("index=" + i + ",value=" + values[i]);
        }

        System.out.println("== inclusive vs exclusive ==");
        for (int i = 1; i < 3; i++) {
            System.out.println("exclusive=" + i);
        }
        for (int i = 1; i <= 3; i++) {
            System.out.println("inclusive=" + i);
        }

        System.out.println("== prefix and range ==");
        System.out.println("first0=" + sumFirst(values, 0));
        System.out.println("first2=" + sumFirst(values, 2));
        System.out.println("first3=" + sumFirst(values, 3));
        System.out.println("range1to3=" + sumRange(values, 1, 3));
        System.out.println("emptyRange=" + sumRange(values, 2, 2));

        System.out.println("== reverse and empty array ==");
        for (int i = values.length - 1; i >= 0; i--) {
            System.out.println("reverse=" + values[i]);
        }
        int[] empty = {};
        int visits = 0;
        for (int i = 0; i < empty.length; i++) {
            visits++;
        }
        System.out.println("emptyVisits=" + visits);

        System.out.println("== one past the end ==");
        int index = 0;
        while (index < values.length) {
            index++;
        }
        System.out.println("indexAfterWhile=" + index);
        try {
            System.out.println("unexpected=" + values[values.length]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("atLength=ArrayIndexOutOfBoundsException");
        }
        try {
            sumFirst(values, 4);
        } catch (IllegalArgumentException ex) {
            System.out.println("count4=" + ex.getMessage());
        }

        System.out.println("== substring uses exclusive end ==");
        String text = "ABCDE";
        System.out.println("slice=" + text.substring(1, 4));
        System.out.println("done");
    }
}
~~~

Tại thư mục chứa file, dùng **JDK 17 trở lên** với PowerShell hoặc Bash:

~~~bash
java -version
javac -version
javac -encoding UTF-8 OffByOneDemo.java
java OffByOneDemo
~~~

**Expected stdout chính xác** của riêng lệnh `java OffByOneDemo`:

~~~text
== array indices ==
length=3
index=0,value=10
index=1,value=20
index=2,value=30
== inclusive vs exclusive ==
exclusive=1
exclusive=2
inclusive=1
inclusive=2
inclusive=3
== prefix and range ==
first0=0
first2=30
first3=60
range1to3=50
emptyRange=0
== reverse and empty array ==
reverse=30
reverse=20
reverse=10
emptyVisits=0
== one past the end ==
indexAfterWhile=3
atLength=ArrayIndexOutOfBoundsException
count4=invalid count
== substring uses exclusive end ==
slice=BCD
done
~~~

Kết quả của `java -version`/`javac -version` phụ thuộc JDK cài đặt, không nằm trong stdout cố định. Mã sử dụng API chuẩn, không yêu cầu thư viện bên ngoài.

## 3. Vì sao `i <= array.length` thường là sai?

~~~java
int[] values = {10, 20, 30};

// SAI nếu truy cập values[i]:
// for (int i = 0; i <= values.length; i++) {
//     System.out.println(values[i]);
// }
~~~

Vòng `i <= values.length` chạy khi `i == 3`, nhưng với mảng dài 3, chỉ các chỉ số 0, 1 và 2 là hợp lệ. Truy cập `values[3]` ném `ArrayIndexOutOfBoundsException`.

Nếu yêu cầu là **duyệt phần tử**, dùng `i < values.length`. Nếu yêu cầu là **duyệt các vị trí ngăn cách giữa phần tử**, có thể cần `i <= values.length`, bởi có `n + 1` vị trí biên, nhưng lúc ấy không được đọc `values[i]` ở vị trí `i == n`.

Nói cách khác, **`<=` không tự động sai**; nó chỉ sai khi không phù hợp với miền giá trị và thao tác trong thân.

## 4. Đếm số lượt khác với truy cập chỉ số

Hai nhiệm vụ có thể dùng điều kiện khác nhau:

~~~java
// Thực hiện hành động đúng 3 lần:
for (int turn = 1; turn <= 3; turn++) {
    System.out.println("turn=" + turn);
}

// Duyệt ba phần tử mảng:
for (int i = 0; i < 3; i++) {
    System.out.println(values[i]);
}
~~~

Cả hai đều chạy ba lượt, nhưng một biến là **số thứ tự lượt** 1..3, một biến là **chỉ số** 0..2. Trộn hai quy ước dễ gây lệch một.

Đối với `count` phần tử đầu của mảng, số phần tử cần xử lý chính là `count`; viết `i < count`. Với `count == 0`, thân phải chạy 0 lần. Nếu viết `i <= count`, ta sẽ xử lý **một phần tử** ngay cả khi yêu cầu là 0 phần tử.

### Đoạn nửa mở giúp ghép các đoạn liền nhau

Ví dụ muốn xử lý các chỉ số thuộc hai đoạn:

~~~text
[0, 2) = 0, 1
[2, 5) = 2, 3, 4
Ghép lại: [0, 5) = 0, 1, 2, 3, 4
~~~

Hai đoạn không chồng nhau và không có lỗ hổng. Với `start == end`, đoạn `[start, end)` **rỗng**, nên lặp 0 lượt là hành vi đúng. API Java `String.substring(beginIndex, endIndex)` cũng sử dụng **biên cuối loại trừ**.

## 5. Duyệt ngược và mảng rỗng

Mảng `n` phần tử có chỉ số cuối hợp lệ là `n - 1`, nên:

~~~java
for (int i = values.length - 1; i >= 0; i--) {
    System.out.println(values[i]);
}
~~~

Nếu `values.length == 0`, giá trị đầu `i == -1` và điều kiện `i >= 0` sai ngay; không đọc phần tử nào. Đây là lý do cách viết này xử lý mảng rỗng đúng.

Tránh mở đầu ở `i = values.length` nếu trong thân sẽ đọc `values[i]`: chỉ số ấy **vượt biên phải một đơn vị**.

Cần đặc biệt cẩn thận với điều kiện như `i > 0`: khi duyệt về 0, nó **bỏ sót phần tử chỉ số 0**. Dùng `i >= 0` nếu muốn bao gồm phần tử đầu.

### Cẩn thận khi đếm kiểu không thích hợp

Java dùng `int` cho chỉ số mảng. Không chuyển biến đếm sang kiểu không hỗ trợ giá trị âm rồi giả định `i >= 0` sẽ kết thúc giống cách dùng `int`. Trong Java, `char` là kiểu không dấu 16 bit; sau decrement và chuyển kiểu, nó có thể quay vòng, nên không phù hợp cho kiểu duyệt ngược dùng điều kiện `>= 0`.

## 6. Kiểm thử các điểm sát biên

Lỗi off-by-one thường lộ ra tại **giá trị sát biên**, không nhất thiết ở đầu vào thông thường.

| Trường hợp kiểm thử | Điều mong đợi |
| --- | --- |
| Mảng rỗng (`length == 0`) | Không truy cập phần tử |
| Mảng 1 phần tử | Đúng 1 lần duyệt; không vượt chỉ số 0 |
| Mảng 3 phần tử | Các chỉ số `0, 1, 2`; không truy cập 3 |
| `count = 0` | Xử lý 0 phần tử |
| `count = length` | Xử lý toàn bộ phần tử, không thừa |
| `count = length + 1` | Bị từ chối nếu tham số là số phần tử cần xử lý |
| `start == endExclusive` | Đoạn rỗng, tổng ban đầu không đổi |
| Duyệt ngược | Đến và bao gồm chỉ số 0 |

Một cách kiểm thử hiệu quả là ghi trước **miền chỉ số hợp lệ**, rồi kiểm chứng ba giá trị: ngay trước biên, đúng tại biên và ngay sau biên. Khi viết vòng `for` hoặc `while`, luôn xác nhận cả **giá trị cuối của biến đếm** lẫn **giá trị cuối thực sự được xử lý trong thân**.

## 7. Lỗi thường gặp

| Nhầm lẫn | Cách đúng |
| --- | --- |
| “Mảng dài `n` có chỉ số cuối `n`.” | Chỉ số cuối là `n - 1` |
| “`i <= array.length` dùng để duyệt mọi phần tử.” | Thường thừa một lượt; dùng `i < array.length` |
| “`i < n` bắt đầu ở 0 thì chạy `n + 1` lần.” | Chạy `n` lần khi `n >= 0` và bước tăng 1 |
| “`for(i=n-1; i>0; i--)` duyệt mọi phần tử.” | Bỏ chỉ số 0 |
| “Đoạn `[start, end)` bao gồm `end`.” | `end` bị loại trừ |
| “Nếu mảng rỗng thì phải truy cập ít nhất một phần tử.” | Duyệt đúng là 0 lần |
| “Chỉ cần test mảng lớn là đủ.” | Các biên 0, 1 và đúng `length` rất quan trọng |
| “Có ngoại lệ thì sửa bằng cách bỏ đi `break` cuối.” | Phải sửa **miền chỉ số và điều kiện** |

## 8. Bài tập tự kiểm tra

1. Với `int[] a = new int[4]`, chỉ số hợp lệ là gì?  
   *Đáp án:* `0, 1, 2, 3`.
2. `for (int i = 0; i <= 4; i++)` chạy bao nhiêu lượt?  
   *Đáp án:* `5` lượt; nếu đọc `a[i]` ở lượt cuối là vượt biên.
3. Đoạn `[2, 6)` chứa mấy số nguyên liên tiếp?  
   *Đáp án:* 4 số (`2, 3, 4, 5`).
4. Duyệt ngược `for (int i = 4; i > 0; i--)` có xử lý `i == 0` không?  
   *Đáp án:* Không.
5. `String "ABCDE".substring(1, 4)` cho gì?  
   *Đáp án:* `"BCD"`.
6. Nếu `count = 0`, vòng `for (int i = 0; i < count; i++)` chạy mấy lần?  
   *Đáp án:* 0 lần.

## Checklist

- [ ] Phân biệt rõ **chỉ số phần tử** với **số lượt**.
- [ ] Biết `n` phần tử có chỉ số `0..n-1`.
- [ ] Dùng đúng biên cuối **loại trừ** với `<` và **bao gồm** với `<=`.
- [ ] Kiểm thử mảng rỗng, 1 phần tử và giá trị đúng sát biên.
- [ ] Duyệt ngược có xét đến chỉ số 0.
- [ ] Ghi rõ quy ước `[start, end)` và kiểm tra `start <= end <= length`.
- [ ] Đảm bảo các biến đếm tiến triển và tránh tràn số nếu biên rất lớn.

**Kết luận:** Off-by-one không chỉ là nhầm dấu `<` thành `<=`, mà là nhầm **ý nghĩa của biên**. Trước khi viết vòng lặp, xác định giá trị đầu được xử lý, giá trị cuối được xử lý, số lượt mong muốn và liệu biên kết thúc có được bao gồm hay không.
