# Duy trì điều kiện bất biến đơn giản qua mỗi lần lặp — Java 17+

## 1. Điều kiện bất biến vòng lặp là gì?

**Bất biến vòng lặp** (*loop invariant*) là một mệnh đề về trạng thái chương trình được giữ đúng **mỗi lần chuẩn bị kiểm tra điều kiện lặp**, kể cả lần kiểm tra cuối cùng khi vòng lặp kết thúc bình thường.

Ví dụ, khi tính tổng mảng từ trái sang phải:

~~~java
int[] numbers = {2, -1, 4, 3};
long sum = 0;

for (int i = 0; i < numbers.length; i++) {
    sum += numbers[i];
}

System.out.println(sum);
~~~

**Exact expected stdout:**

~~~text
8
~~~

Một bất biến hữu ích ở **đầu mỗi lượt** là:

> `sum` bằng tổng của **đúng `i` phần tử đầu tiên**: `numbers[0]` đến `numbers[i-1]`.

Với `i = 0`, chưa xử lý phần tử nào nên `sum = 0`. Với `i = 2`, đã xử lý `2` và `-1` nên `sum = 1`. Khi vòng lặp hoàn tất với `i = numbers.length`, bất biến cho biết `sum` là tổng của toàn mảng.

Bất biến không phải từ khóa hay cú pháp Java; đó là **khẳng định logic** do người viết code xác định, lý giải và có thể kiểm tra trong lúc debug/test.

## 2. Ba bước chứng minh một bất biến

| Bước | Câu hỏi cần trả lời | Ví dụ tính tổng tiền tố |
|---|---|---|
| **Khởi tạo** (*initialization*) | Mệnh đề có đúng trước lượt đầu? | `i=0`, `sum=0` là tổng tiền tố rỗng |
| **Bảo toàn** (*maintenance*) | Nếu đúng trước lượt này, chạy body và update xong có còn đúng? | Cộng `numbers[i]`, rồi `i++`; tổng ứng với tiền tố dài hơn một phần tử |
| **Kết thúc** (*termination*) | Khi điều kiện lặp sai, bất biến suy ra kết quả gì? | `i=n` nên `sum` là tổng của `n` phần tử |

~~~mermaid
flowchart TD
    A["Khởi tạo: bất biến đúng"] --> B{"Điều kiện lặp đúng?"}
    B -- "Đúng" --> C["Thực thi thân vòng lặp"]
    C --> D["Cập nhật biến đếm"]
    D --> E["Bất biến vẫn đúng"]
    E --> B
    B -- "Sai" --> F["Bất biến + điều kiện dừng"]
    F --> G["Suy ra hậu điều kiện/kết quả"]
~~~

**Phân biệt quan trọng:** Ba bước trên chủ yếu chứng minh **tính đúng từng phần**: nếu vòng lặp kết thúc, kết quả là đúng. Để chứng minh nó **chắc chắn kết thúc**, cần thêm lập luận về sự tiến triển, thường dùng một đại lượng giảm dần (*loop variant*).

## 3. Xác định thời điểm bất biến phải đúng

Xét:

~~~java
for (int i = 0; i < numbers.length; i++) {
    sum += numbers[i];
}
~~~

Bất biến được mô tả tại **đầu vòng lặp, trước kiểm tra điều kiện**. Sau dòng `sum += numbers[i]` nhưng **trước khi `i++` chạy**, biến `sum` đã là tổng `i+1` phần tử, còn `i` vẫn có giá trị cũ. Vì vậy mệnh đề “`sum` là tổng `i` phần tử” không nhất thiết đúng **tại mọi dòng trung gian**.

Sau update `i++`, đầu lượt kế tiếp ta lại có:

- `i` mới = `i` cũ + 1.
- `sum` = tổng của `i` mới phần tử đầu tiên.
- Bất biến được **khôi phục đúng tại điểm kiểm tra**.

Điểm này giúp tránh lỗi lập luận: bất biến phải đúng ở **các điểm kiểm tra đã xác định**, không cần bất biến đúng sau từng phép gán trong body.

## 4. Truy vết bất biến tổng tiền tố

Mảng `{2, -1, 4, 3}`, khởi tạo `sum = 0`:

| Đầu lượt / khi dừng | `i` | Tiền tố đã xử lý | `sum` |
|---|---:|---|---:|
| Trước lượt đầu | 0 | Rỗng | 0 |
| Trước lượt thứ 2 | 1 | `[2]` | 2 |
| Trước lượt thứ 3 | 2 | `[2, -1]` | 1 |
| Trước lượt thứ 4 | 3 | `[2, -1, 4]` | 5 |
| Khi `i < 4` sai | 4 | `[2, -1, 4, 3]` | 8 |

**Cách bảo toàn:**

Giả sử trước lượt có `0 <= i < n` và `sum = numbers[0] + ... + numbers[i-1]`.

1. Thân vòng lặp thực hiện `sum += numbers[i]`.
2. Update của `for` thực hiện `i++`.
3. Tại đầu lượt kế, `sum` là tổng phần tử có chỉ số từ 0 đến `i-1` theo `i` mới.

**Kết thúc:** điều kiện `i < n` sai và `i` được tăng từng đơn vị từ 0. Khi không có thay đổi bất thường hoặc overflow chỉ số, `i=n`. Kết hợp bất biến, kết quả đúng bằng tổng cả mảng.

**Giả định dữ liệu:** ví dụ dùng `long` làm tổng để có miền lớn hơn `int`. Với dữ liệu thực tế có thể khiến `long` tràn, cần phép toán được kiểm tra hoặc `BigInteger`; không thể dùng phép cộng tràn mà vẫn coi kết quả là tổng toán học chính xác.

## 5. Chọn bất biến đủ mạnh để suy ra kết quả

Một mệnh đề như “`i >= 0`” thường đúng trong vòng duyệt mảng, nhưng **không đủ** để chứng minh tổng tính được là đúng.

Với thuật toán tính tổng, ta nên duy trì đồng thời:

- **Giới hạn biến đếm:** `0 <= i <= n`.
- **Quan hệ với dữ liệu đã xử lý:** `sum` là tổng tiền tố dài `i`.

Khi điều kiện dừng cho `i == n`, cả hai mệnh đề kết hợp mới suy ra `sum` là tổng toàn bộ mảng.

**Mẹo thiết kế:** từ **hậu điều kiện mong muốn** (“tổng của tất cả phần tử”), thay cụm “tất cả” thành “những phần tử đã xử lý” và gắn với biến đếm `i`. Đó thường là một bất biến đơn giản, dễ chứng minh.

## 6. Ví dụ thứ hai: tìm phần tử lớn nhất

Với một mảng **không rỗng**:

~~~java
int[] data = {-3, 5, 1, 7, 7};
int best = data[0];

for (int i = 1; i < data.length; i++) {
    if (data[i] > best) {
        best = data[i];
    }
}

System.out.println(best);
~~~

**Exact expected stdout:**

~~~text
7
~~~

**Bất biến tại đầu mỗi lượt:** `best` là **giá trị lớn nhất** trong tiền tố `data[0..i-1]`, với `1 <= i <= data.length`.

- **Khởi tạo:** trước lượt đầu `i=1`, tiền tố gồm một phần tử `data[0]`; `best=data[0]` là lớn nhất của tiền tố đó.
- **Bảo toàn:** ở lượt `i`, so `data[i]` với `best`; sau khi cập nhật, `best` là max của tiền tố dài `i+1`. Sau `i++`, bất biến đúng với chỉ số mới.
- **Kết thúc:** khi `i=data.length`, tiền tố chính là toàn bộ mảng, nên `best` là giá trị lớn nhất của mảng.

**Biên quan trọng:** mảng rỗng không có `data[0]`; phải từ chối đầu vào rỗng hoặc định nghĩa một API kết quả tùy chọn. Đặt `best = 0` cho mọi mảng là **sai** với mảng chỉ chứa số âm.

Nếu có nhiều phần tử cùng lớn nhất, code trên trả về **giá trị lớn nhất**, không cam kết chỉ số của lần xuất hiện cuối hay đầu. Muốn trả vị trí, cần một bất biến có thêm biến chỉ số.

## 7. Ví dụ thứ ba: tìm vị trí xuất hiện đầu tiên

~~~java
static int findFirst(int[] data, int target) {
    for (int i = 0; i < data.length; i++) {
        if (data[i] == target) {
            return i;
        }
    }
    return -1;
}
~~~

**Bất biến tại đầu lượt `i`:** không có phần tử nào trong **các vị trí `0..i-1`** bằng `target`.

- **Khởi tạo:** `i=0` thì tiền tố rỗng, mệnh đề đúng.
- **Bảo toàn:** nếu `data[i] != target`, tiếp tục sang `i+1` và tiền tố chưa tìm thấy được mở rộng thêm một vị trí.
- **Nếu tìm thấy:** `data[i] == target`; mọi vị trí trước `i` đã được chứng minh khác target, nên `i` là **vị trí đầu tiên**.
- **Nếu duyệt hết:** `i=n`, tất cả vị trí đều khác target; trả `-1` là đúng.

Ví dụ:

~~~java
int[] data = {4, 6, 2, 6};
System.out.println(findFirst(data, 6)); // 1
System.out.println(findFirst(data, 9)); // -1
~~~

Mã trên minh họa logic; phương thức `findFirst` cần nằm cùng lớp hoặc được gọi qua tên lớp chứa phương thức.

**Chú ý:** một `return` khi tìm thấy là **kết thúc sớm hợp lệ**. Lập luận đúng đắn khi đó dùng bất biến của tiền tố cộng với điều kiện tìm thấy, không phụ thuộc việc vòng lặp phải chạy đến `i=n`.

## 8. Bất biến không đồng nghĩa điều kiện dừng

Hai điều khác nhau:

- **Loop invariant:** điều luôn đúng ở điểm kiểm tra được chọn, dùng để chứng minh **tính đúng kết quả**.
- **Loop variant** (*đại lượng tiến triển*): một đại lượng không âm và giảm dần theo mỗi lượt tiếp tục, thường dùng để chứng minh **kết thúc**.

Ví dụ:

~~~java
for (int remaining = 3; remaining > 0; remaining--) {
    System.out.println("remaining=" + remaining);
}
~~~

**Exact stdout:**

~~~text
remaining=3
remaining=2
remaining=1
~~~

Bất biến: `0 <= remaining && remaining <= 3` ở mỗi đầu lượt, kể cả lúc `remaining=0` và điều kiện đã false. Variant có thể chọn chính `remaining`: khi vẫn lặp, nó là số nguyên dương và mỗi lần update giảm 1, nên cuối cùng đạt 0.

Bất biến **một mình** không ngăn vòng lặp vô hạn:

~~~java
int i = 0;
// while (i >= 0) {
//     // i không đổi, điều kiện luôn true, bất biến i >= 0 vẫn đúng.
// }
~~~

Để bảo đảm dừng, phải có **tiến triển thực sự** và xét tác động của `break`, `continue`, phép cập nhật cũng như khả năng tràn số.

## 9. `break`, `continue` và bất biến

Với `for` ba phần:

- `continue;` bỏ phần body còn lại nhưng **vẫn chạy update** rồi kiểm tra lượt kế. Bất biến cần được bảo toàn cho mọi đường đi dùng `continue`.
- `break;` thoát vòng ngay, **không chạy update cuối**. Nếu cần một hậu điều kiện cho nhánh `break`, hãy chứng minh riêng rằng điều kiện tại vị trí break là đủ.
- `return` kết thúc phương thức; hậu điều kiện của giá trị trả về phải được chứng minh theo đường đi đó.

Một lỗi phổ biến:

~~~java
int[] data = {3, -1, 4};
int sum = 0;

for (int i = 0; i < data.length; i++) {
    if (data[i] < 0) {
        continue;
    }
    sum += data[i];
}
~~~

Code này trả **7**, không phải tổng **6** của mảng. Nếu mục tiêu thật sự là **tổng phần tử không âm**, bất biến đúng phải được viết lại: `sum` bằng tổng các giá trị không âm trong tiền tố đã xử lý.

**Bất biến phải phản ánh đúng yêu cầu bài toán và các nhánh điều khiển**, không chỉ giống một mẫu có sẵn.

## 10. Tác dụng của kiểm tra bất biến khi debug

Bạn có thể tạm tạo một hàm **tính lại tổng tiền tố** rồi so sánh với trạng thái trong mỗi lượt:

~~~java
static long prefixSum(int[] data, int limit) {
    long result = 0;
    for (int k = 0; k < limit; k++) {
        result += data[k];
    }
    return result;
}

static void requireInvariant(boolean condition) {
    if (!condition) {
        throw new IllegalStateException("loop invariant violated");
    }
}
~~~

Trong thuật toán tính tổng:

~~~java
for (int i = 0; i < data.length; i++) {
    requireInvariant(sum == prefixSum(data, i));
    sum += data[i];
}
requireInvariant(sum == prefixSum(data, data.length));
~~~

- Mỗi lần kiểm tra đầu lượt xác nhận mệnh đề đang được duy trì.
- Lần kiểm tra **sau vòng lặp** xác nhận mệnh đề ở trạng thái kết thúc.
- Nếu sai, `IllegalStateException` giúp phát hiện lỗi sớm.

**Giới hạn:** phép kiểm tra này chạy một vòng lặp phụ để tính tổng tiền tố, nên tổng chi phí debug có thể từ `O(n)` thành **`O(n²)`**. Chỉ dùng cho bài học, test hoặc dữ liệu nhỏ; trong production nên bỏ hoặc chỉ bật có kiểm soát.

Bạn cũng có thể dùng `assert` của Java:

~~~java
assert sum == prefixSum(data, i) : "bad prefix sum";
~~~

Tuy nhiên, Java **tắt assertions theo mặc định**; phải chạy với `java -ea ...` mới kiểm tra. Không dùng `assert` làm cơ chế xác thực dữ liệu bắt buộc hoặc để thay lập luận đúng đắn.

## 11. Chương trình Java 17 hoàn chỉnh

Tạo file đúng tên **`LoopInvariantDemo.java`**:

~~~java
public final class LoopInvariantDemo {
    private LoopInvariantDemo() {}

    static void requireInvariant(boolean condition) {
        if (!condition) {
            throw new IllegalStateException("loop invariant violated");
        }
    }

    static long prefixSum(int[] data, int limit) {
        long total = 0;
        for (int k = 0; k < limit; k++) {
            total += data[k];
        }
        return total;
    }

    static long sum(int[] data) {
        if (data == null) {
            throw new IllegalArgumentException("data must not be null");
        }

        long total = 0;
        for (int i = 0; i < data.length; i++) {
            // Invariant: total == sum of data[0..i-1].
            requireInvariant(total == prefixSum(data, i));
            System.out.println("sum entry i=" + i + " total=" + total);
            total += data[i];
        }

        requireInvariant(total == prefixSum(data, data.length));
        System.out.println("sum final=" + total);
        return total;
    }

    static int prefixMax(int[] data, int limit) {
        int result = data[0];
        for (int k = 1; k < limit; k++) {
            if (data[k] > result) {
                result = data[k];
            }
        }
        return result;
    }

    static int max(int[] data) {
        if (data == null || data.length == 0) {
            throw new IllegalArgumentException("requires nonempty array");
        }

        int best = data[0];
        for (int i = 1; i < data.length; i++) {
            // Invariant: best == max of data[0..i-1].
            requireInvariant(best == prefixMax(data, i));
            System.out.println("max entry i=" + i + " best=" + best);
            if (data[i] > best) {
                best = data[i];
            }
        }

        requireInvariant(best == prefixMax(data, data.length));
        System.out.println("max final=" + best);
        return best;
    }

    static int findFirst(int[] data, int target) {
        if (data == null) {
            throw new IllegalArgumentException("data must not be null");
        }

        for (int i = 0; i < data.length; i++) {
            // Invariant: data[k] != target for all 0 <= k < i.
            for (int k = 0; k < i; k++) {
                requireInvariant(data[k] != target);
            }
            System.out.println("scan i=" + i + " value=" + data[i]);
            if (data[i] == target) {
                return i;
            }
        }
        System.out.println("not found");
        return -1;
    }

    static int countdown() {
        int ticks = 0;
        for (int remaining = 3; remaining > 0; remaining--) {
            // Invariant: 0 <= remaining <= 3.
            requireInvariant(remaining >= 0 && remaining <= 3);
            System.out.println("remaining=" + remaining);
            ticks++;
        }
        return ticks;
    }

    public static void main(String[] args) {
        System.out.println("== sum ==");
        System.out.println("sum result=" + sum(new int[]{2, -1, 4, 3}));

        System.out.println("== max ==");
        System.out.println("max result=" + max(new int[]{-3, 5, 1, 7, 7}));

        try {
            max(new int[]{});
        } catch (IllegalArgumentException ex) {
            System.out.println("max empty=" + ex.getMessage());
        }

        System.out.println("== find first ==");
        int[] input = {4, 6, 2, 6};
        System.out.println("first 6=" + findFirst(input, 6));
        System.out.println("first 9=" + findFirst(input, 9));

        System.out.println("== termination ==");
        System.out.println("ticks=" + countdown());
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal tại thư mục chứa `LoopInvariantDemo.java`. Chỉ dùng thư viện tiêu chuẩn JDK; không cần Maven, Gradle hoặc preview feature.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 LoopInvariantDemo.java
java -cp . LoopInvariantDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\LoopInvariantDemo.java
java -cp . LoopInvariantDemo
~~~

### Exact expected stdout

~~~text
== sum ==
sum entry i=0 total=0
sum entry i=1 total=2
sum entry i=2 total=1
sum entry i=3 total=5
sum final=8
sum result=8
== max ==
max entry i=1 best=-3
max entry i=2 best=5
max entry i=3 best=5
max entry i=4 best=7
max final=7
max result=7
max empty=requires nonempty array
== find first ==
scan i=0 value=4
scan i=1 value=6
first 6=1
scan i=0 value=4
scan i=1 value=6
scan i=2 value=2
scan i=3 value=6
not found
first 9=-1
== termination ==
remaining=3
remaining=2
remaining=1
ticks=3
~~~

**Đọc kết quả:**

1. `sum`: trước mỗi lượt, `total` đúng bằng tổng tiền tố đã xử lý; sau vòng, tổng bằng 8.
2. `max`: `best` là max của các phần tử đã xét; chạy với mảng toàn âm vẫn đúng; mảng rỗng được từ chối.
3. `findFirst`: trước mỗi lượt kiểm tra rằng không có kết quả ở tiền tố trước `i`; thấy 6 tại vị trí 1 thì trả ngay; không có 9 nên trả -1.
4. `countdown`: bất biến giới hạn `remaining` được giữ; variant giảm từ 3 xuống 0 nên vòng kết thúc.
5. Các hàm `prefixSum`/`prefixMax`/vòng kiểm tra tiền tố dùng để **xác minh trong demo**, làm tăng chi phí chạy. Khi tối ưu, giữ nguyên lập luận bất biến nhưng bỏ kiểm tra lặp thừa.

## 12. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Gọi `i < n` là bất biến | Nó sai khi vòng kết thúc bình thường | Dùng `0 <= i <= n` cho giới hạn chỉ số |
| Viết bất biến chỉ là `sum >= 0` | Không đúng nếu mảng có số âm; không chứng minh tổng | Dùng mệnh đề tổng tiền tố |
| Giả định bất biến đúng ngay sau mọi câu lệnh | Có thể sai giữa body và update | Xác định rõ điểm kiểm tra đầu lượt |
| Bỏ qua bước khởi tạo | Mệnh đề không chắc đúng trước lượt đầu | Chứng minh trường hợp tiền tố rỗng/1 phần tử |
| Chỉ chứng minh bảo toàn mà không nối với hậu điều kiện | Chưa chứng minh kết quả cuối | Ghép bất biến với điều kiện dừng |
| Có bất biến nhưng không có tiến triển | Vẫn có thể lặp vô hạn | Chọn variant giảm dần, kiểm tra update |
| Khởi tạo max bằng 0 | Sai với mảng chỉ có số âm | Lấy phần tử đầu, xử lý mảng rỗng |
| Thêm `continue` nhưng giữ bất biến cũ không phù hợp | Bất biến không phản ánh phần tử bị bỏ | Định nghĩa lại tiền tố đã xử lý / yêu cầu |
| Dùng `break` rồi kết luận như trường hợp `i=n` | Kết thúc sớm có điều kiện khác | Chứng minh riêng đường `break`/`return` |
| Kiểm tra bất biến bằng vòng phụ ở mọi lượt trong production | Dễ làm thuật toán `O(n)` thành `O(n²)` | Chỉ dùng trong test/debug |
| Tin rằng `assert` luôn hoạt động | Mặc định JVM không bật assertions | Dùng `-ea` trong test, không dùng làm kiểm tra bắt buộc |
| Không xét overflow ở tổng số nguyên | Kết quả có thể khác tổng toán học | Dùng kiểu đủ lớn hoặc kiểm tra overflow |

## 13. Bài tập có đáp án

### Bài A — viết bất biến của tổng tiền tố

~~~java
long total = 0;
for (int i = 0; i < data.length; i++) {
    total += data[i];
}
~~~

**Đáp án:** tại đầu mỗi lượt, `0 <= i <= data.length` và `total` là tổng `data[0..i-1]`. Sau điều kiện dừng `i=data.length`, tổng là toàn mảng (giả định phép cộng không overflow).

### Bài B — vì sao khởi tạo max bằng 0 sai?

~~~java
int[] data = {-8, -3, -10};
int best = 0; // Sai nếu bài toán là max của toàn mảng.
~~~

**Đáp án:** 0 không phải phần tử của mảng và lớn hơn tất cả giá trị. Khởi tạo `best=data[0]`, duyệt từ `i=1`; kết quả đúng là `-3`.

### Bài C — bất biến khi tìm phần tử đầu tiên

~~~java
for (int i = 0; i < data.length; i++) {
    if (data[i] == target) return i;
}
return -1;
~~~

**Đáp án:** trước lượt `i`, không phần tử nào trong `data[0..i-1]` bằng target. Khi gặp target, `i` là vị trí đầu tiên; khi duyệt hết, target không có trong mảng.

### Bài D — bất biến có bảo đảm dừng không?

~~~java
int i = 0;
// while (i == 0) { /* không đổi i */ }
~~~

**Đáp án:** mệnh đề `i == 0` vẫn đúng nhưng vòng có thể chạy mãi. Muốn chứng minh kết thúc phải có biến tiến triển và điều kiện dừng đạt được.

### Bài E — `continue` thay đổi mục tiêu tính tổng

~~~java
int[] data = {3, -1, 4};
int total = 0;
for (int i = 0; i < data.length; i++) {
    if (data[i] < 0) continue;
    total += data[i];
}
System.out.println(total);
~~~

**Đáp án:** in `7`. Bất biến phù hợp là “tổng các phần tử **không âm** đã xử lý”, không phải tổng mọi phần tử tiền tố.

## 14. Checklist và kết luận

- [ ] Phân biệt bất biến vòng lặp với **điều kiện tiếp tục lặp**.
- [ ] Xác định rõ **điểm** mà bất biến phải đúng (đầu mỗi lượt).
- [ ] Chứng minh **khởi tạo**, **bảo toàn**, **kết thúc**.
- [ ] Viết bất biến gắn trực tiếp với kết quả mong muốn, ví dụ tổng/max của tiền tố đã xử lý.
- [ ] Dùng điều kiện dừng cùng bất biến để suy ra kết quả.
- [ ] Phân biệt bất biến với **loop variant** dùng để chứng minh kết thúc.
- [ ] Kiểm tra đường `continue`, `break`, `return` để không giả định sai trạng thái.
- [ ] Xét trường hợp mảng rỗng, chỉ số biên, số âm và overflow.
- [ ] Biết công cụ debug có thể xác nhận bất biến trên bộ test nhưng không thay thế chứng minh logic.
- [ ] Hiểu bật assertions bằng `-ea`; không phụ thuộc assert cho validation bắt buộc.
- [ ] Chạy `LoopInvariantDemo.java` bằng Java 17+ và đối chiếu exact stdout.

**Kết luận:** Bất biến vòng lặp là **mối liên hệ được giữ qua từng lượt** giữa trạng thái tích lũy và phần dữ liệu đã xử lý. Thiết kế bất biến đủ mạnh, chứng minh nó đúng ở đầu lượt, bảo toàn qua body/update, rồi kết hợp với điều kiện dừng sẽ giải thích **tại sao thuật toán đúng**, chứ không chỉ cho thấy ví dụ chạy đúng.