# `for` với phần khởi tạo, điều kiện và cập nhật — Java 17+

## 1. Vòng lặp `for` truyền thống là gì?

Trong Java, `for` truyền thống (*basic for statement*) thích hợp khi cần **khởi tạo trạng thái**, **kiểm tra điều kiện trước mỗi lượt**, rồi **cập nhật trạng thái sau lượt**. Cú pháp:

~~~java
for (initialization; condition; update) {
    // loop body
}
~~~

Ví dụ đếm từ 0 đến 2:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println("i=" + i);
}
~~~

**Exact expected stdout:**

~~~text
i=0
i=1
i=2
~~~

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| **Khởi tạo** (*initialization*) | `int i = 0` | Chạy **một lần** trước lượt đầu |
| **Điều kiện** (*condition*) | `i < 3` | Kiểm tra **trước mỗi lượt**, phải là `boolean` hoặc `Boolean` có thể unboxing |
| **Cập nhật** (*update*) | `i++` | Chạy **sau thân vòng lặp**, trước khi kiểm tra điều kiện tiếp |
| **Thân vòng lặp** (*body*) | `System.out.println(...)` | Chạy khi điều kiện đúng |

Dấu chấm phẩy giữa ba phần trong ngoặc là **bắt buộc** ngay cả khi một phần bị bỏ trống. Đừng nhầm với `for (Type item : collection)` (*enhanced for*), có cú pháp và mục tiêu khác.

## 2. Thứ tự thực thi chính xác

Với `for (int i = 0; i < 2; i++)`, thứ tự là:

~~~text
Khởi tạo i = 0 (một lần)
    ↓
Kiểm tra i < 2
    ├── false → kết thúc for
    └── true
          ↓
       Thân vòng lặp
          ↓
       Cập nhật i++
          ↓
       Quay lại kiểm tra i < 2
~~~

~~~mermaid
flowchart TD
    A["Chạy initialization một lần"] --> B{"condition đúng?"}
    B -- "Không" --> E["Rời vòng for"]
    B -- "Có" --> C["Chạy body"]
    C --> D["Chạy update"]
    D --> B
~~~

Có thể quan sát từng bước bằng hàm in log:

~~~java
static int init() {
    System.out.println("init");
    return 0;
}

static boolean check(int i) {
    System.out.println("check " + i);
    return i < 2;
}

static int next(int i) {
    System.out.println("update " + i);
    return i + 1;
}

// Trong main:
for (int i = init(); check(i); i = next(i)) {
    System.out.println("body " + i);
}
~~~

**Exact expected stdout:**

~~~text
init
check 0
body 0
update 0
check 1
body 1
update 1
check 2
~~~

**Điểm cần nhớ:** Sau lượt cuối vẫn có bước **update**, rồi **condition** được kiểm tra và trả false. Khi điều kiện ban đầu false thì body và update **không chạy**.

## 3. Phần khởi tạo: chỉ chạy một lần

Phần `initialization` thường khai báo và khởi tạo biến đếm:

~~~java
for (int index = 0; index < 4; index++) {
    System.out.println(index);
}
~~~

Biến đếm cũng có thể được **khai báo từ trước**:

~~~java
int index = 0;
for (; index < 3; index++) {
    // Dùng biến index đã có.
}
System.out.println(index); // 3
~~~

Lúc đó initialization bị bỏ trống nhưng **dấu `;` đầu vẫn phải có**.

Java còn cho khai báo **nhiều biến cùng một kiểu** trong phần khởi tạo:

~~~java
for (int left = 0, right = 6; left < right; left++, right--) {
    System.out.println(left + ":" + right);
}
~~~

**Exact expected stdout:**

~~~text
0:6
1:5
2:4
~~~

Không khai báo hai kiểu khác nhau trong **cùng một danh sách khai báo**:

~~~java
// Không hợp lệ:
// for (int i = 0, long j = 3; i < 3; i++) { }
~~~

Nếu cần các loại biến khác nhau, khai báo chúng trước `for`.

## 4. Phần điều kiện: kiểu boolean, được xét trước mỗi lượt

Ví dụ:

~~~java
int count = 0;
for (int i = 5; i < 5; i++) {
    count++;
}
System.out.println(count); // 0
~~~

Vì `5 < 5` sai ngay lúc bắt đầu nên không có lượt lặp nào.

Java không có kiểu “truthy” theo nghĩa số khác 0 tự thành true:

~~~java
// Sai: int không dùng trực tiếp làm điều kiện.
// for (int i = 3; i; i--) { }
~~~

Sửa bằng điều kiện boolean rõ ràng:

~~~java
for (int i = 3; i != 0; i--) {
    System.out.println(i);
}
~~~

**Exact expected stdout:**

~~~text
3
2
1
~~~

Nếu điều kiện là `Boolean` có thể null, Java sẽ cần **unboxing** lúc xét; null gây `NullPointerException`. Trong vòng lặp cơ bản nên dùng `boolean` nguyên thủy hoặc xử lý null có chủ đích.

## 5. Phần cập nhật: chạy sau body, không phải trước body

Cập nhật thường là `i++`, `i--`, `i += 2` hoặc một danh sách các biểu thức cập nhật:

~~~java
for (int i = 0; i <= 6; i += 2) {
    System.out.println(i);
}
~~~

**Exact expected stdout:**

~~~text
0
2
4
6
~~~

Nếu danh sách cập nhật có hai biểu thức:

~~~java
for (int a = 0, b = 4; a < b; a++, b--) {
    System.out.println(a + "/" + b);
}
~~~

**Exact expected stdout:**

~~~text
0/4
1/3
~~~

Các biểu thức cập nhật được thực thi **theo thứ tự từ trái sang phải**. Trong vị trí update, `i++` và `++i` có cùng tác dụng lên `i` khi kết quả biểu thức không được dùng, dù ở ngữ cảnh khác hậu tố và tiền tố có thể trả giá trị khác nhau.

**Không phải** mọi biểu thức Java đều được dùng tùy ý ở initializer/update: danh sách này phải gồm những *statement expressions* hợp lệ, chẳng hạn gán, tăng/giảm, gọi phương thức hay tạo đối tượng; không thể đặt trần `i + 1` để thay `i++`.

## 6. Có thể bỏ trống ba thành phần, nhưng phải kiểm soát kết thúc

Một hoặc nhiều thành phần của `for` có thể bỏ trống:

~~~java
int cursor = 0;
for (; cursor < 3;) {
    System.out.println(cursor);
    cursor++; // Cập nhật bên trong body.
}
~~~

**Exact expected stdout:**

~~~text
0
1
2
~~~

Nếu bỏ hẳn điều kiện, nó được xem là **luôn true**:

~~~java
int attempts = 0;
for (;;) {
    attempts++;
    if (attempts == 3) {
        break;
    }
}
System.out.println(attempts); // 3
~~~

`for (;;)` là dạng vòng lặp vô hạn theo cú pháp; muốn có điểm thoát phải thiết kế `break`, `return`, `throw` hoặc cơ chế dừng khác.

**Nguy cơ:** `for (int i = 0; i < 3; )` mà body không tăng `i` có thể không bao giờ kết thúc nếu không có đường thoát khác. Bỏ trống update chỉ nên dùng khi cơ chế thay đổi điều kiện nằm ở nơi rõ ràng.

## 7. `break` và `continue` tác động đến update ra sao?

Trong **basic for**:

- `break;` thoát ngay vòng lặp; không chạy phần update của lượt đang bị ngắt.
- `continue;` bỏ phần còn lại của body, nhưng **vẫn chạy update của for**, sau đó mới kiểm tra điều kiện lượt kế.
- `return` kết thúc phương thức; không tiếp tục update của vòng lặp ấy.
- Nếu có exception làm thoát vòng lặp, update cũng không tự chạy như một phần `finally`.

~~~java
for (int i = 0; i < 5; i++) {
    if (i == 2) {
        System.out.println("continue=" + i);
        continue;
    }
    if (i == 4) {
        System.out.println("break=" + i);
        break;
    }
    System.out.println("visit=" + i);
}
~~~

**Exact expected stdout:**

~~~text
visit=0
visit=1
continue=2
visit=3
break=4
~~~

Sau `continue=2`, update `i++` vẫn diễn ra nên lượt kế là 3. Sau `break=4`, vòng lặp kết thúc ngay.

**Phân biệt với `while`:** khi tự đặt `i++` cuối body của `while`, một `continue` ở phía trước có thể bỏ qua thao tác tăng và gây lặp mãi. Với `for` truyền thống, update nằm ở phần thứ ba vẫn được chạy sau `continue` thông thường.

## 8. Phạm vi biến đếm: khai báo ở trong hay ngoài `for`?

Một biến được khai báo trong `ForInit` dùng được ở điều kiện, phần cập nhật và thân của **chính** vòng đó; nó không còn thuộc phạm vi sau vòng:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
// System.out.println(i); // Không biên dịch: i đã ngoài phạm vi.
~~~

Nếu ứng dụng cần biết giá trị cuối sau vòng, khai báo biến **trước** `for`:

~~~java
int index = 0;
for (; index < 3; index++) {
    // Có thể dùng index ở đây.
}
System.out.println(index); // 3.
~~~

Không khai báo lại biến cục bộ cùng tên khi phạm vi còn chồng lấn. Biến đếm đang thay đổi trong `update` cũng không phải biến **effectively final** để lambda bắt trực tiếp; có thể sao chép giá trị của nó vào một biến cục bộ trong từng lượt nếu cần.

Ở bài này, phạm vi là điều cần nhớ để dùng đúng ba thành phần `for`. Bài **vòng đời biến đếm** đi sâu vào thời điểm khởi tạo lại, `continue`/`break`, phạm vi lồng nhau và truy vết biến theo từng lượt.


## 9. Duyệt mảng với đúng biên

Mảng dài `n` chỉ có chỉ số hợp lệ `0..n-1`:

~~~java
int[] values = {4, 7, 9};
int total = 0;
for (int i = 0; i < values.length; i++) {
    total += values[i];
}
System.out.println(total); // 20.
~~~

Điều kiện đúng để **đọc phần tử** là `i < values.length`, không phải `i <= values.length`: ở lượt `i == length`, truy cập `values[i]` sẽ ném `ArrayIndexOutOfBoundsException`. Ngược lại, khi bài toán thật sự cần **bao gồm** đầu mút, `<=` hoàn toàn có thể đúng.

Duyệt ngược từ cuối mảng thường viết `for (int i = values.length - 1; i >= 0; i--)`; mảng rỗng sẽ lặp 0 lượt. Điều kiện đầu, bước cập nhật và biên cuối luôn phải tương thích. Bài **lỗi lệch một đơn vị** phân tích sâu đoạn nửa mở `[start,end)`, truy cập mảng rỗng và kiểm thử biên.


## 10. `for` lồng nhau: initializer của vòng trong chạy lại

~~~java
int cells = 0;
for (int row = 0; row < 2; row++) {
    for (int col = 0; col < 3; col++) {
        cells++;
    }
}
System.out.println(cells); // 6.
~~~

Ở đây vòng ngoài có 2 lượt; mỗi lượt **khởi tạo lại `col = 0`**, rồi vòng trong chạy 3 lượt. Tổng là `2 × 3 = 6`. Nếu giới hạn vòng trong phụ thuộc `row`, không thể luôn nhân hai kích thước cố định: phải cộng số lượt trong của từng lượt ngoài.

Với thân chi phí hằng số và cận độc lập `n`, `m`, độ phức tạp là `O(nm)`. Bài **vòng lặp lồng nhau** sẽ truy vết từng cặp biến đếm, duyệt mảng hai chiều không đều và phân biệt `break`/`continue` có nhãn.


## 11. Chọn cú pháp để ý định rõ ràng

| Công việc | Lựa chọn thường dễ đọc |
| --- | --- |
| Cần chỉ số hoặc thay đổi biến đếm rõ ràng | Basic `for (init; condition; update)` |
| Chỉ cần lần lượt lấy giá trị từng phần tử | Enhanced `for (Type value : array)` |
| Số lượt phụ thuộc sự kiện/trạng thái bên ngoài | `while` |
| Phải thử thân ít nhất một lần rồi mới kiểm tra | `do-while` |

~~~java
int[] numbers = {4, 7, 9};
for (int i = 0; i < numbers.length; i++) {
    System.out.println("index=" + i + ",value=" + numbers[i]);
}
for (int value : numbers) {
    System.out.println("value=" + value);
}
~~~

Enhanced `for` không phơi bày ba thành phần của basic `for`; nếu cần truy cập bằng chỉ số, hãy dùng basic `for`. Với collection, sửa cấu trúc trong lúc đang duyệt còn liên quan tới hợp đồng của iterator. Không có loại vòng nào luôn nhanh hơn các loại khác. Bài **chọn loại vòng lặp** sẽ so sánh điểm kiểm tra điều kiện và các tình huống thực hành.


## 12. Chương trình Java 17 hoàn chỉnh

Tạo file **`BasicForThreePartsDemo.java`** với đúng nội dung:

~~~java
public final class BasicForThreePartsDemo {
    private BasicForThreePartsDemo() {}

    static int init() {
        System.out.println("init");
        return 0;
    }

    static boolean check(int i) {
        System.out.println("check " + i);
        return i < 2;
    }

    static int update(int i) {
        System.out.println("update " + i);
        return i + 1;
    }

    public static void main(String[] args) {
        System.out.println("== order ==");
        for (int i = init(); check(i); i = update(i)) {
            System.out.println("body " + i);
        }

        System.out.println("== basic ==");
        for (int i = 0; i < 3; i++) {
            System.out.println("i=" + i);
        }

        System.out.println("== zero iterations ==");
        int count = 0;
        for (int i = 4; i < 4; i++) {
            count++;
        }
        System.out.println("count=" + count);

        System.out.println("== two variables ==");
        for (int left = 0, right = 6;
                left < right; left++, right--) {
            System.out.println("pair=" + left + ":" + right);
        }

        System.out.println("== continue and break ==");
        for (int i = 0; i < 5; i++) {
            if (i == 2) {
                System.out.println("continue=" + i);
                continue;
            }
            if (i == 4) {
                System.out.println("break=" + i);
                break;
            }
            System.out.println("visit=" + i);
        }

        System.out.println("== array ==");
        int[] numbers = {4, 7, 9};
        int total = 0;
        for (int i = 0; i < numbers.length; i++) {
            total += numbers[i];
        }
        System.out.println("sum=" + total);

        System.out.println("== nested ==");
        int cells = 0;
        for (int r = 0; r < 2; r++) {
            for (int c = 0; c < 3; c++) {
                cells++;
            }
        }
        System.out.println("cells=" + cells);

        System.out.println("== omitted parts ==");
        int cursor = 0;
        for (; cursor < 3;) {
            System.out.println("cursor=" + cursor);
            cursor++;
        }

        int attempts = 0;
        for (;;) {
            attempts++;
            if (attempts == 3) {
                break;
            }
        }
        System.out.println("infinite break=" + attempts);

        System.out.println("== outer variable ==");
        int index = 0;
        for (; index < 3; index++) {
            // Body can be empty.
        }
        System.out.println("after i=" + index);
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal ở thư mục chứa file; không dùng thư viện ngoài JDK, Maven hay Gradle.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 BasicForThreePartsDemo.java
java -cp . BasicForThreePartsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\BasicForThreePartsDemo.java
java -cp . BasicForThreePartsDemo
~~~

### Exact expected stdout

~~~text
== order ==
init
check 0
body 0
update 0
check 1
body 1
update 1
check 2
== basic ==
i=0
i=1
i=2
== zero iterations ==
count=0
== two variables ==
pair=0:6
pair=1:5
pair=2:4
== continue and break ==
visit=0
visit=1
continue=2
visit=3
break=4
== array ==
sum=20
== nested ==
cells=6
== omitted parts ==
cursor=0
cursor=1
cursor=2
infinite break=3
== outer variable ==
after i=3
~~~

Đối chiếu: `init` một lần; `check` chạy trước mỗi body và cả lượt kiểm tra cuối thất bại; `update` chạy sau body bình thường/continue; cặp hai biến kết thúc khi `left == right`; array có `4+7+9=20`; vòng lồng nhau có `2×3=6`; vòng `for (;;)` thoát nhờ `break`.

## 13. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nhầm init chạy mỗi lượt | Hiểu sai thứ tự hoặc chi phí | Init chỉ chạy **một lần** |
| Nhầm update chạy trước body | Lệch giá trị hiển thị | Order: init → condition → body → update |
| `i <= array.length` khi lấy `array[i]` | Truy cập vượt cuối mảng | `i < array.length` |
| `for (int i=0; i; i++)` | Không biên dịch, điều kiện `int` | Dùng biểu thức boolean |
| Bỏ update mà body cũng không đổi biến | Nguy cơ lặp vô hạn | Thêm cập nhật hoặc đường thoát |
| Dùng `i++` khi muốn đếm ngược | Sai chiều lặp | Dùng `i--` với điều kiện thích hợp |
| Tưởng `continue` bỏ cả update trong `for` | Sai luồng điều khiển | Basic `for` vẫn thực hiện update |
| Tưởng `break` vẫn chạy update trước khi thoát | Sai giá trị cuối | `break` bỏ update |
| Dùng `i` sau vòng khi khai báo trong init | Không thuộc phạm vi | Khai báo `i` ngoài vòng nếu cần |
| `for(int i=0, long j=0;...)` | Cú pháp sai ở phần khai báo | Dùng cùng kiểu hoặc khai báo trước |
| Viết `i + 1` trong update | Không phải statement expression hợp lệ | Viết `i++`, `i += 1` hoặc `i = i + 1` |
| Dùng biến `int` tăng tới `Integer.MAX_VALUE` mà không xét overflow | Có thể tràn và lặp sai | Chọn điều kiện/kiểu phù hợp, kiểm tra biên |
| Cố dùng `for` ba phần khi chỉ cần đọc từng phần tử | Code dài, dễ lỗi chỉ số | Cân nhắc enhanced `for` |
| Tạo `for (...); { ... }` vô tình | Dấu `;` kết thúc loop với body rỗng | Bỏ `;` thừa trước block |

## 14. Bài tập có đáp án

### Bài A — in số chẵn từ 0 tới 8

~~~java
for (int i = 0; i <= 8; i += 2) {
    System.out.println(i);
}
~~~

**Expected stdout:**

~~~text
0
2
4
6
8
~~~

### Bài B — đếm ngược từ 3 tới 1

~~~java
for (int i = 3; i >= 1; i--) {
    System.out.println(i);
}
~~~

**Expected stdout:**

~~~text
3
2
1
~~~

### Bài C — có bao nhiêu lượt?

~~~java
int count = 0;
for (int i = 10; i < 10; i++) {
    count++;
}
System.out.println(count);
~~~

**Đáp án:** `0`. Điều kiện sai trước body đầu tiên.

### Bài D — tìm lỗi khi duyệt mảng

~~~java
int[] data = {1, 2, 3};
// for (int i = 0; i <= data.length; i++) {
//     System.out.println(data[i]);
// }
~~~

**Đáp án:** sửa `i <= data.length` thành `i < data.length`. Chỉ số cuối là 2, không phải 3.

### Bài E — `continue` có làm tăng `i` không?

~~~java
for (int i = 0; i < 4; i++) {
    if (i == 1) continue;
    System.out.println(i);
}
~~~

**Expected stdout:**

~~~text
0
2
3
~~~

Với `i == 1`, `continue` chuyển sang bước **update `i++`**, rồi điều kiện được xét lại. Không bị kẹt ở 1.

### Bài F — hai biến trong cùng `for`

~~~java
for (int a = 0, b = 5; a < b; a++, b--) {
    System.out.println(a + ":" + b);
}
~~~

**Expected stdout:**

~~~text
0:5
1:4
2:3
~~~

Đến bước cập nhật kế, `a == 3`, `b == 2`, điều kiện `a < b` sai.

## 15. Checklist và kết luận

- [ ] Viết được cấu trúc `for (init; condition; update) { body }`.
- [ ] Nhớ init **một lần**, condition **trước mỗi lượt**, update **sau body**.
- [ ] Hiểu vòng lặp có thể chạy **0 lượt** khi điều kiện đầu tiên false.
- [ ] Biết điều kiện phải là `boolean`/`Boolean`, không phải số nguyên truthy/falsy.
- [ ] Dùng được nhiều biến cùng kiểu ở init và nhiều biểu thức update.
- [ ] Biết cách bỏ trống một phần, vẫn giữ hai dấu `;`.
- [ ] Nhận ra `for (;;)` cần thiết kế cơ chế thoát.
- [ ] Phân biệt `continue` vẫn chạy update với `break` thoát ngay.
- [ ] Hiểu phạm vi biến đếm khai báo bên trong init.
- [ ] Tránh lỗi off-by-one bằng `i < array.length`.
- [ ] Biết khi nào dùng basic `for`, enhanced `for`, hay `while`.
- [ ] Chạy `BasicForThreePartsDemo.java` với `javac`/`java` trên JDK 17+ và đối chiếu exact stdout.

**Kết luận:** Trong Java 17+, ba phần của basic `for` biểu diễn rõ **thiết lập ban đầu**, **điều kiện tiếp tục** và **bước thay đổi sau mỗi lượt**. Để tránh lỗi, hãy kiểm tra thứ tự `init → condition → body → update`, bảo đảm điều kiện có thể kết thúc, và chú ý phạm vi biến cùng các giá trị tại biên.