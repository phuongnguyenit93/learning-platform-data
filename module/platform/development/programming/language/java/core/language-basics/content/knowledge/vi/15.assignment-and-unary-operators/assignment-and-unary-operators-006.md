# Phân biệt giá trị biểu thức với giá trị biến sau `++` hoặc `--`

## 1. Luôn theo dõi hai đại lượng

Mỗi lần gặp tiền tố/hậu tố, hãy ghi riêng **giá trị biểu thức cung cấp cho phép tính bên ngoài** và **trạng thái của biến sau cập nhật**. Bốn quy tắc nền tảng là: `x++`/`x--` cung cấp giá trị **cũ** rồi cập nhật biến; `++x`/`--x` cập nhật biến và cung cấp giá trị **mới**. Việc cập nhật đã xảy ra ngay trong lần đánh giá này.

Với hai ví dụ độc lập:

~~~java
int x = 5;
int a = x++; // a=5, x=6

int y = 5;
int b = ++y; // b=6, y=6
~~~

| Biểu thức | Giá trị đưa vào phép gán ngoài | Trạng thái biến sau đó |
|---|---:|---:|
| `x++` với `x=5` | 5 | `x=6` |
| `++x` với `x=5` | 6 | `x=6` |
| `x--` với `x=5` | 5 | `x=4` |
| `--x` với `x=5` | 4 | `x=4` |

Đây là **hai thông tin khác nhau**, dù một số ví dụ có cùng số ở cả hai cột. Bài “Tăng giảm tiền tố và hậu tố” giải thích cú pháp và cách dùng trong vòng lặp; bài này tập trung vào **phương pháp truy vết kết quả khi biểu thức được sử dụng**.

## 2. Bảng truy vết: đọc giá trị ở đúng thời điểm

Với mỗi dòng Java, có thể làm theo trình tự:

1. Viết trạng thái biến **trước biểu thức**.
2. Xác định vị trí của `++`/`--` và ghi **giá trị mà toán tử cung cấp**.
3. Cập nhật trạng thái biến ngay khi toán tử được đánh giá.
4. Đọc các toán hạng tiếp theo theo thứ tự đánh giá của Java, tính kết quả ngoài.
5. Ghi **cả kết quả và trạng thái cuối**; không thay một giá trị bằng giá trị kia.

Ví dụ có **một** lần hậu tố và một lần đọc trạng thái sau:

~~~java
int x = 5;
int result = x++ * 10 + x;
~~~

| Bước | Giá trị dùng cho phép tính | `x` đang giữ |
|---|---:|---:|
| Ban đầu | — | 5 |
| `x++` | 5 | 6 |
| `5 * 10` | 50 | 6 |
| Đọc `x` ở toán hạng cuối | 6 | 6 |
| Cộng | `result = 56` | 6 |

Với tiền tố:

~~~java
int y = 5;
int result = ++y * 10 + y;
// result=66, y=6
~~~

`++y` cung cấp 6 và biến đã bằng 6 khi toán hạng sau đọc. Kết quả cuối **không thể suy ra chỉ từ số lần xuất hiện của ký hiệu `++`** mà phải theo dõi thời điểm đọc.

## 3. Biến nhận kết quả và biến bị cập nhật có thể khác nhau

~~~java
int score = 10;
int snapshot = score++;
int current = score;
System.out.println(snapshot); // 10
System.out.println(current);  // 11
~~~

`snapshot` lưu **giá trị biểu thức hậu tố**; `current` đọc **trạng thái sau hậu tố**. Nếu ghi log “`score++` trả 11” chỉ vì log sau đó thấy `score=11`, bạn đã nhập nhằng hai thời điểm khác nhau.

Một bẫy khi biến nhận và biến bị cập nhật là cùng một biến:

~~~java
int n = 5;
n = n++;
System.out.println(n); // 5
~~~

`n++` trước hết làm `n` thành 6 nhưng **trả 5**; phép gán ngoài lưu lại 5. Vì vậy dòng này không dùng để tăng biến. Khi chỉ muốn cập nhật trạng thái, viết riêng `n++;`. Những chuỗi có **nhiều** lần tăng giảm trong một biểu thức được phân tích và viết lại ở bài cuối chương.

## 4. Phân biệt tăng chỉ số với tăng phần tử mảng

Hai dòng sau có toán tử đặt tại **hai vị trí khác nhau**:

~~~java
int[] items = {7, 9};
int index = 0;
int picked = items[index++];
// picked=7, index=1, items vẫn là {7,9}
~~~

`index++` trả chỉ số cũ 0, sau đó tăng **index**; không thay đổi giá trị của `items[0]`.

~~~java
int[] items = {7, 9};
int previous = items[0]++;
// previous=7, items[0]=8, items[1]=9
~~~

Ở đây `++` gắn với **biến phần tử mảng `items[0]`**, không phải chỉ số. Khi debug, ghi rõ “biến nào bị thay đổi” cùng với “biểu thức trả gì”.

## 5. Giá trị cũ tại biên số và với wrapper

~~~java
int max = Integer.MAX_VALUE;
int old = max++;
// old=2147483647, max=-2147483648
~~~

Hậu tố cung cấp giá trị cũ ngay cả khi cập nhật làm `int` tràn. Java không tự ném ngoại lệ overflow ở phép `++` này. Nếu cần phát hiện tràn, cân nhắc `Math.incrementExact` và thiết kế riêng cách trả giá trị cũ.

Với `Integer nullable`, `++` cần unboxing; `Integer absent = null; absent++;` sẽ ném `NullPointerException`. Bảng truy vết chỉ kết thúc bình thường khi từng bước đánh giá thành công.

## 6. Chương trình Java 17+ để đối chiếu bảng

Lưu thành `IncrementExpressionValueDemo.java`:

~~~java
public final class IncrementExpressionValueDemo {
    public static void main(String[] args) {
        int post = 5;
        int postValue = post++;
        System.out.println("post=" + postValue + "," + post);

        int pre = 5;
        int preValue = ++pre;
        System.out.println("pre=" + preValue + "," + pre);

        int x = 5;
        int withPost = x++ * 10 + x;
        System.out.println("tracePost=" + withPost + "," + x);

        int y = 5;
        int withPre = ++y * 10 + y;
        System.out.println("tracePre=" + withPre + "," + y);

        int overwritten = 5;
        overwritten = overwritten++;
        System.out.println("overwritten=" + overwritten);

        int[] items = {7, 9};
        int index = 0;
        int picked = items[index++];
        System.out.println("index=" + picked + "," + index + "," + items[0]);

        int previous = items[0]++;
        System.out.println("element=" + previous + "," + items[0]);

        int max = Integer.MAX_VALUE;
        int old = max++;
        System.out.println("overflow=" + old + "," + max);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 IncrementExpressionValueDemo.java
java IncrementExpressionValueDemo
~~~

**Expected stdout:**

~~~text
post=5,6
pre=6,6
tracePost=56,6
tracePre=66,6
overwritten=5
index=7,1,7
element=7,8
overflow=2147483647,-2147483648
~~~

Các dòng `tracePost`/`tracePre` kiểm tra thời điểm toán hạng cuối đọc biến; `index`/`element` cho thấy vị trí tăng khác nhau; `overwritten` phân biệt tác dụng phụ tạm thời với trạng thái cuối sau phép gán ngoài.

## 7. Bài tập có đáp án

**Bài A.** `int x = 3; int y = x-- * 10 + x;`. **Đáp án:** `y=32`, `x=2` vì `x--` cung cấp 3 rồi `x` mới là 2.

**Bài B.** `int x = 3; int y = --x * 10 + x;`. **Đáp án:** `y=22`, `x=2` vì `--x` cung cấp 2 và lần đọc sau vẫn là 2.

**Bài C.** `int[] data = {4,5}; int i=0; int a=data[i++];`. **Đáp án:** `a=4`, `i=1` và mảng không đổi.

**Bài D.** `int[] data = {4,5}; int a=data[0]++;`. **Đáp án:** `a=4` và `data[0]=5`.

**Bài E.** Giải thích `int n=9; n=n++;`. **Đáp án:** `n` cuối cùng vẫn là 9 vì kết quả cũ của hậu tố bị phép gán ngoài ghi trở lại.

## 8. Tự kiểm tra trước khi chuyển bài

- [ ] Phân biệt được **giá trị biểu thức** và **giá trị đang lưu**.
- [ ] Biết hậu tố cập nhật ngay, không chờ lệnh kế tiếp.
- [ ] Vẽ được bảng truy vết của một phép tăng/giảm nằm trong phép tính.
- [ ] Chỉ ra biến nào đổi khi `++` nằm ở chỉ số hoặc phần tử mảng.
- [ ] Giải thích được phép gán ngoài ghi đè `x++` mà không gọi Java là undefined.
- [ ] Biết giá trị cũ vẫn được trả khi cập nhật bị overflow.

**Ghi nhớ:** Để hiểu `++`/`--` bên trong biểu thức, hãy trả lời **hai câu riêng**: *toán tử vừa cung cấp giá trị gì* và *biến nào đang giữ giá trị gì*. Với biểu thức có nhiều lần cập nhật trên cùng biến, cần thêm bảng thứ tự đánh giá và cân nhắc tách các side effect thành từng câu lệnh.
