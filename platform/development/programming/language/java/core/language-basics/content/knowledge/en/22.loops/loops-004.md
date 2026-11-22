# Vòng đời biến đếm trong `for` — Java 17+

Vòng lặp `for` cơ bản thường dùng **biến đếm** để theo dõi số lần lặp hoặc vị trí đang xử lý. Hiểu đúng *lúc biến được khởi tạo, lúc nào nó thay đổi và phạm vi sử dụng* giúp tránh lỗi lệch một đơn vị, dùng biến ngoài phạm vi và vòng lặp không kết thúc.

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
// In lần lượt: 0, 1, 2.
~~~

Trong ví dụ này, `i` được **khai báo và khởi tạo một lần** khi câu lệnh `for` bắt đầu, lần lượt mang các giá trị 0, 1, 2 trong thân; sau khi cập nhật thành 3 thì điều kiện sai và vòng lặp kết thúc. Biến `i` **không còn nằm trong phạm vi truy cập** sau câu lệnh `for` vì được khai báo trong phần khởi tạo.

## 1. Phân biệt giá trị biến đếm với phạm vi của tên

Trong `for (int i = 0; i < 3; i++)`, phần `int i = 0` chỉ chạy **một lần mỗi khi chương trình đi vào câu lệnh `for`**; chính biến `i` ấy nhận giá trị 0, 1, 2 qua các lượt thân. Sau lượt cuối, phép cập nhật đưa `i` lên 3 rồi điều kiện sai. Nếu khai báo `i` ở đầu `for`, mã sau vòng **không được tham chiếu tên `i`**; đây là quy tắc phạm vi tại lúc biên dịch, không phải phép kiểm tra giá trị lúc chạy.

| Tình huống | Điều cần theo dõi |
| --- | --- |
| Một câu `for` chạy nhiều lượt | Khởi tạo một lần, cập nhật sau mỗi lượt bình thường hoặc `continue` nhắm tới vòng |
| Câu `for` nằm trong vòng ngoài hoặc phương thức được gọi lại | **Mỗi lần đi vào câu lệnh** là một lần khởi tạo mới |
| `break` dừng giữa chừng | Không có lần cập nhật cuối của vòng bị thoát |
| Biến khai báo trong `for` | Dùng được ở điều kiện, cập nhật, thân; hết phạm vi sau `for` |
| Biến khai báo trước `for` | Vẫn trong phạm vi sau vòng để kiểm tra giá trị cuối |

Vì thế, khi muốn quan sát giá trị sau vòng, hãy khai báo biến bên ngoài. Khi muốn giới hạn biến đếm cho đúng một thao tác duyệt, khai báo ở đầu `for` thường an toàn và dễ đọc. Các ví dụ dưới đây tập trung vào **phạm vi, lần tái khởi tạo và những đường thoát**, còn thứ tự ba thành phần được giới thiệu ở bài `for` trước đó.
## 2. Chương trình Java 17+ có thể chạy bằng CLI

Tạo tệp UTF-8 tên **`ForCounterLifecycleDemo.java`**:

~~~java
public class ForCounterLifecycleDemo {
    static void zeroIterations() {
        for (int i = 3; i < 3; i++) {
            System.out.println("unreachable");
        }
        System.out.println("zero=done");
    }

    static void declaredOutside() {
        int index = 0;
        for (; index < 3; index++) {
            System.out.println("external=" + index);
        }
        System.out.println("externalAfter=" + index);
    }

    static int step(int i) {
        System.out.println("step=" + i);
        return i + 1;
    }

    static void continueAndBreak() {
        for (int i = 0; i < 4; i = step(i)) {
            if (i == 1) {
                System.out.println("continueAt=1");
                continue;
            }
            if (i == 3) {
                System.out.println("breakAt=3");
                break;
            }
            System.out.println("seen=" + i);
        }
    }

    static void nested() {
        for (int row = 0; row < 2; row++) {
            for (int col = 0; col < 2; col++) {
                System.out.println("grid=" + row + "," + col);
            }
        }
    }

    static void twoCounters() {
        for (int left = 0, right = 3;
             left < right;
             left++, right--) {
            System.out.println("pair=" + left + "," + right);
        }
    }

    static void repeatedEntry() {
        for (int run = 1; run <= 2; run++) {
            int sum = 0;
            for (int i = 0; i < 2; i++) {
                sum += i;
            }
            System.out.println("run=" + run + ",sum=" + sum);
        }
    }

    public static void main(String[] args) {
        System.out.println("== initial false ==");
        zeroIterations();

        System.out.println("== outer scope ==");
        declaredOutside();

        System.out.println("== continue and break ==");
        continueAndBreak();

        System.out.println("== nested ==");
        nested();

        System.out.println("== two counters ==");
        twoCounters();

        System.out.println("== re-enter ==");
        repeatedEntry();
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) trong thư mục chứa file; sử dụng **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ForCounterLifecycleDemo.java
java ForCounterLifecycleDemo
~~~

**Exact expected stdout** của riêng lệnh `java ForCounterLifecycleDemo`:

~~~text
== initial false ==
zero=done
== outer scope ==
external=0
external=1
external=2
externalAfter=3
== continue and break ==
seen=0
step=0
continueAt=1
step=1
seen=2
step=2
breakAt=3
== nested ==
grid=0,0
grid=0,1
grid=1,0
grid=1,1
== two counters ==
pair=0,3
pair=1,2
== re-enter ==
run=1,sum=1
run=2,sum=1
~~~

Đầu ra `java -version` và `javac -version` thay đổi theo môi trường, không nằm trong khối stdout cố định. Chương trình không cần thư viện bên ngoài.

## 3. Phạm vi biến đếm phụ thuộc vị trí khai báo

### Khai báo ngay trong `for`

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i); // Hợp lệ.
}
// System.out.println(i); // KHÔNG biên dịch: i ngoài phạm vi.
~~~

Phạm vi của `i` khai báo trong **ForInit** bao gồm những phần liên quan của câu lệnh `for`: điều kiện, cập nhật và thân. Khi câu lệnh kết thúc, tên `i` không còn dùng được bên ngoài.

Nói “biến tồn tại đến khi thoát vòng” là một cách diễn đạt trực quan về phạm vi; compiler quyết định **có được truy cập biến hay không** theo phạm vi khai báo, không phải theo việc liệu bộ nhớ vật lý của biến đã bị giải phóng hay chưa.

### Khai báo trước `for`

~~~java
int i = 0;
for (; i < 3; i++) {
    System.out.println(i);
}
System.out.println("after=" + i); // after=3.
~~~

Vì `i` được khai báo bên ngoài, nó **vẫn trong phạm vi** sau khi vòng lặp kết thúc. Chỗ khởi tạo trong đầu `for` có thể để trống nhưng vẫn phải giữ dấu `;`.

Khi đã có `int i` trong cùng phạm vi bao quanh, không được khai báo lại `int i` trong phần khởi tạo của một `for` lồng ở phạm vi xung đột:

~~~java
int i = 10;
// for (int i = 0; i < 3; i++) { } // Lỗi khai báo trùng tên.
for (int j = 0; j < 3; j++) { } // Hợp lệ.
~~~

Ngược lại, hai câu `for (int i = ... )` **nối tiếp** có thể khai báo cùng tên `i` vì phạm vi vòng trước đã kết thúc.

## 4. `continue`, `break` và phần cập nhật

**`continue`** trong `for` cơ bản bỏ các câu lệnh còn lại của lần lặp, nhưng vẫn đi tới **phần cập nhật** trước khi kiểm tra điều kiện tiếp. Demo cho thấy:

~~~text
seen=0
step=0
continueAt=1
step=1
seen=2
step=2
breakAt=3
~~~

Cụ thể: gặp `continue` tại `i == 1`, Java vẫn gọi `step(1)`, nhận 2 rồi kiểm tra điều kiện. Gặp `break` ở `i == 3`, Java rời vòng lặp **ngay**: không có `step=3`.

| Đường thực thi | Phần cập nhật có chạy? |
| --- | --- |
| Thân kết thúc bình thường | Có |
| `continue;` nhắm tới vòng `for` này | Có |
| `break;` thoát vòng này | Không |
| `return;` / `throw ...;` từ thân | Không theo luồng bình thường |
| Điều kiện false trước thân | Không |

Với vòng lặp lồng nhau hoặc `continue`/`break` có nhãn, phải xét **câu lệnh mà lệnh điều khiển nhắm tới**, không kết luận mọi `continue` đều chạy cập nhật của mọi vòng `for`.

## 5. Biến đếm không tự động bắt đầu từ 0

`for` không gắn biến với quy ước 0, 1, 2...; người viết quyết định giá trị ban đầu, điều kiện và cách cập nhật:

~~~java
for (int n = 5; n >= 1; n--) {
    System.out.print(n + " ");
}
// In: 5 4 3 2 1 (có dấu cách cuối).
~~~

Có thể dùng **hai biến cùng kiểu** trong phần khởi tạo và nhiều biểu thức cập nhật, ngăn bằng dấu phẩy:

~~~java
for (int left = 0, right = 3;
     left < right;
     left++, right--) {
    System.out.println(left + "," + right);
}
// In: 0,3 rồi 1,2.
~~~

Phần điều kiện trong `for` là **một biểu thức boolean**, không phải danh sách điều kiện bằng dấu phẩy. Dùng `&&` hoặc `||` nếu cần ghép điều kiện. Phần cập nhật cũng không bắt buộc là `i++`: có thể dùng `i += 2` hoặc một phép gán khác, miễn bảo đảm vòng lặp có cơ chế kết thúc phù hợp.

**Thân `for` có thể chạy 0 lần** nếu điều kiện false ngay sau khởi tạo. Trong ví dụ `for (int i = 3; i < 3; i++)`, chỉ có phần khởi tạo và kiểm tra đầu tiên; không chạy thân hoặc cập nhật.

## 6. Mỗi lần đi vào câu lệnh `for` là một lần khởi tạo mới

Khi cùng một câu lệnh `for` được thực hiện lại (ví dụ nằm trong thân một vòng ngoài hoặc phương thức được gọi lần nữa), phần khởi tạo của nó chạy **lại từ đầu**.

~~~java
for (int run = 1; run <= 2; run++) {
    for (int i = 0; i < 2; i++) {
        System.out.print(i);
    }
    System.out.println();
}
// In hai dòng: 01 rồi 01.
~~~

Biến `i` của vòng trong bắt đầu từ 0 mỗi lần câu lệnh vòng trong được đi vào; nó **không tiếp tục từ giá trị của lần chạy trước**.

Trong hai vòng lặp lồng nhau, dùng tên khác nhau như `row` và `col` để biểu đạt từng vai trò. Đổi nhầm biến ở điều kiện hoặc cập nhật có thể khiến vòng lặp chạy sai hoặc không kết thúc.

### Phân biệt `for` cơ bản với enhanced `for`

~~~java
int[] numbers = {4, 5};
for (int value : numbers) {
    System.out.println(value);
}
~~~

Đây là **enhanced for**. Biến `value` đại diện cho phần tử ở từng lượt; không có ba phần khởi tạo/điều kiện/cập nhật do người viết nêu rõ. Không lấy quy tắc `i++` trong basic `for` áp nguyên vẹn cho dạng này.

## 7. Các lỗi thường gặp

| Hiểu nhầm | Quy tắc đúng |
| --- | --- |
| “`int i = 0` trong `for` chạy lại ở mọi lượt.” | Khởi tạo chỉ một lần **mỗi lần đi vào câu lệnh for** |
| “`i` khai báo trong `for` dùng được sau vòng.” | Không; đã ra ngoài phạm vi |
| “`continue` bỏ cả phần cập nhật.” | Trong basic `for`, cập nhật vẫn chạy nếu `continue` nhắm tới vòng đó |
| “`break` vẫn chạy `i++` thêm lần nữa.” | Không |
| “`for` luôn thực hiện ít nhất một lượt.” | Có thể chạy 0 lượt |
| “Hai vòng `for` nối tiếp không được dùng cùng tên `i`.” | Được, nếu phạm vi khai báo không chồng lấn |
| “Mọi biến đếm bắt buộc là `int` hoặc bắt đầu từ 0.” | Chọn kiểu/khởi đầu phù hợp; miễn cú pháp và điều kiện hợp lệ |
| “`for (int i = 0; i < n; i++);` có thân là khối sau.” | Dấu `;` khiến vòng có **thân rỗng** |

**Tránh vòng vô hạn và tràn số:** Luôn xác nhận cập nhật đưa biến tiến tới điều kiện dừng. Với số nguyên cố định độ rộng, `i++` có thể tràn và quay vòng; đừng mặc định mọi phép tăng sẽ đạt một mốc toán học bất kỳ.

## 8. Bài tập tự kiểm tra

1. `for (int i=0; i<3; i++)`: thân chạy những giá trị nào?  
   *Đáp án:* 0, 1, 2; giá trị 3 chỉ được dùng ở lần kiểm tra cuối.
2. `i` khai báo trong đầu `for` có thể in sau dấu `}` của vòng lặp không?  
   *Đáp án:* Không, nằm ngoài phạm vi.
3. Nếu `int i=0; for (;i<2;i++) {}` thì sau vòng `i` bằng mấy?  
   *Đáp án:* 2.
4. Khi thân gặp `continue` nhắm tới basic `for`, Java làm gì tiếp?  
   *Đáp án:* Thực hiện phần cập nhật rồi kiểm tra điều kiện.
5. Nếu thân gặp `break` thì phần cập nhật có chạy không?  
   *Đáp án:* Không.
6. `for (int i=4; i<4; i++)` chạy thân bao nhiêu lần?  
   *Đáp án:* 0 lần.
7. Khi vòng `for` nằm trong vòng ngoài được thực hiện hai lần, phần khởi tạo vòng trong chạy mấy lần?  
   *Đáp án:* Hai lần, mỗi lần đi vào vòng trong một lần.

## Checklist

- [ ] Nhớ thứ tự **khởi tạo → kiểm tra → thân → cập nhật → kiểm tra lại**.
- [ ] Biết biến đếm khai báo trong ForInit nằm trong phạm vi của vòng, không ở ngoài.
- [ ] Phân biệt biến khai báo **trước vòng** với biến khai báo **trong đầu vòng**.
- [ ] Hiểu `continue` (nhắm tới vòng) vẫn thực hiện cập nhật, còn `break` thì không.
- [ ] Biết phần khởi tạo chạy lại khi cả câu lệnh `for` được đi vào lần khác.
- [ ] Kiểm tra điều kiện ban đầu, cập nhật và điểm dừng để tránh lặp sai/vô hạn.

**Kết luận:** Biến đếm trong basic `for` có một vòng đời cú pháp rõ ràng: được khởi tạo khi vào vòng, kiểm tra và cập nhật qua từng lượt, và chỉ được truy cập trong phạm vi khai báo. Nắm chắc thứ tự thực thi cùng `continue`/`break` giúp dự đoán đúng giá trị biến và viết vòng lặp an toàn.
