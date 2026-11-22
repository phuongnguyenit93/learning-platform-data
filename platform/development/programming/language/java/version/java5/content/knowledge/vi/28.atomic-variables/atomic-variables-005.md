# Phân biệt incrementAndGet với getAndIncrement

## 1. Cả hai đều tăng nguyên tử, khác ở kết quả trả về

`incrementAndGet()` và `getAndIncrement()` là hai phương thức của `AtomicInteger` và `AtomicLong`. Cả hai đều cộng 1 vào giá trị đang quản lý bằng một thao tác nguyên tử. Khác biệt quan trọng là **lấy giá trị trước hay sau lần tăng của chính lời gọi đó**.

Giả sử bộ đếm hiện tại là `n`, chưa xét tràn số:

| Phương thức | Giá trị trả về | Giá trị lưu sau phép tăng |
| --- | --- | --- |
| `getAndIncrement()` | `n` | `n + 1` |
| `incrementAndGet()` | `n + 1` | `n + 1` |

Với hai bộ đếm độc lập cùng bắt đầu bằng 5:

```java
AtomicInteger a = new AtomicInteger(5);
int first = a.getAndIncrement(); // first = 5; a lưu 6.

AtomicInteger b = new AtomicInteger(5);
int second = b.incrementAndGet(); // second = 6; b lưu 6.
```

Cách nhớ: `getAndIncrement` lấy giá trị cũ để trả rồi tăng; `incrementAndGet` tăng rồi trả giá trị mới. Đây là cách giải thích kết quả API, không phải chỉ dẫn tự triển khai bằng hai lời gọi rời. Xem [AtomicInteger](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html).

## 2. Không ghép lại bằng get và phép cộng

Các đoạn sau không tương đương về đồng bộ với một phép tăng nguyên tử:

```java
// Minh họa sai khi counter có cập nhật cạnh tranh.
int old = counter.get();
counter.set(old + 1);
```

Nếu hai luồng cùng đọc một giá trị, chúng có thể cùng ghi một kết quả, làm mất một lần tăng. Tương tự, cách sau tăng đúng nhưng không lấy được chắc chắn kết quả gắn với lần tăng của mình:

```java
counter.incrementAndGet();
int value = counter.get(); // Có thể đã có luồng khác tăng thêm.
```

Nếu cần kết quả sau lần tăng, hãy nhận trực tiếp:

```java
int value = counter.incrementAndGet();
```

Nếu cần kết quả trước lần tăng, nhận từ `getAndIncrement()`. Một lời gọi cung cấp cả cập nhật và kết quả tương ứng, thay vì đọc lại dữ liệu dùng chung vào một thời điểm khác.

Về kết quả trả về, có thể liên hệ `incrementAndGet()` với tiền tố `++x`, `getAndIncrement()` với hậu tố `x++`. Nhưng phép tăng một biến `int` thông thường không có bảo đảm nguyên tử của các phương thức này; sự giống nhau chỉ giúp nhớ giá trị trả về.

## 3. Chọn theo ý nghĩa của bộ đếm

### Bộ đếm lưu “số sẽ cấp tiếp theo”

Nếu `nextId` bắt đầu bằng 100 và lần cấp đầu phải nhận 100, dùng:

```java
long id = nextId.getAndIncrement();
```

Sau lời gọi, bộ đếm chuẩn bị 101 cho lần sau. Giá trị khởi tạo là số đầu tiên muốn cấp.

### Bộ đếm lưu “số đã cấp cuối cùng”

Nếu `lastId` bắt đầu bằng 99 và lần cấp đầu phải nhận 100, dùng:

```java
long id = lastId.incrementAndGet();
```

Sau lời gọi, giá trị lưu và số vừa cấp đều là 100. Tên trường nên thể hiện quy ước này để tránh đổi API nhưng quên đổi giá trị khởi tạo.

### Đếm số việc vừa hoàn thành

Nếu số hoàn tất bắt đầu 0, `int total = completed.incrementAndGet()` cho tổng sau khi ghi nhận một việc nữa. Nếu muốn dùng số cũ làm chỉ số bắt đầu từ 0, `getAndIncrement()` có thể phù hợp hơn.

Đây là lựa chọn về kết quả, không phải hai mức độ an toàn khác nhau. Nếu chỉ gọi phương thức rồi bỏ giá trị trả về, trong cùng một chuỗi thao tác cả hai đều có tác dụng tăng 1 giống nhau. Không có cơ sở chọn một phương thức vì suy đoán tên của nó “nguyên tử hơn”.

## 4. Ví dụ đầy đủ: tuần tự và hai luồng

Ví dụ dưới đây chạy trên JDK 17 trở lên. Phần đồng thời có hai tác vụ, mỗi tác vụ tăng ba lần. Kết quả được thu lại rồi sắp xếp để quan sát tập giá trị trả về, không suy luận từ thứ tự in của các luồng.

Lưu thành `IncrementReturnDemo.java`:

```java
import java.util.TreeSet;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntSupplier;

public class IncrementReturnDemo {
    private static int[] callThreeTimes(IntSupplier operation) {
        int[] values = new int[3];
        for (int i = 0; i < values.length; i++) {
            values[i] = operation.getAsInt();
        }
        return values;
    }

    private static TreeSet<Integer> collect(
            ExecutorService pool, IntSupplier operation) throws Exception {
        Future<int[]> first = pool.submit(() -> callThreeTimes(operation));
        Future<int[]> second = pool.submit(() -> callThreeTimes(operation));
        TreeSet<Integer> sorted = new TreeSet<>();
        for (int value : first.get()) {
            sorted.add(value);
        }
        for (int value : second.get()) {
            sorted.add(value);
        }
        return sorted;
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger oldCounter = new AtomicInteger(5);
        int oldResult = oldCounter.getAndIncrement();
        System.out.println("old result=" + oldResult
                + ", stored=" + oldCounter.get());

        AtomicInteger newCounter = new AtomicInteger(5);
        int newResult = newCounter.incrementAndGet();
        System.out.println("new result=" + newResult
                + ", stored=" + newCounter.get());

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            AtomicInteger before = new AtomicInteger();
            TreeSet<Integer> oldValues = collect(pool, before::getAndIncrement);
            System.out.println("old values=" + oldValues
                    + ", stored=" + before.get());

            AtomicInteger after = new AtomicInteger();
            TreeSet<Integer> newValues = collect(pool, after::incrementAndGet);
            System.out.println("new values=" + newValues
                    + ", stored=" + after.get());
        } finally {
            pool.shutdownNow();
        }

        AtomicInteger shared = new AtomicInteger();
        int mine = shared.incrementAndGet();
        Thread other = new Thread(() -> shared.incrementAndGet());
        other.start();
        other.join();
        System.out.println("mine=" + mine + ", latest=" + shared.get());
    }
}
```

Biên dịch và chạy:

```shell
javac IncrementReturnDemo.java
java IncrementReturnDemo
```

Stdout:

```text
old result=5, stored=6
new result=6, stored=6
old values=[0, 1, 2, 3, 4, 5], stored=6
new values=[1, 2, 3, 4, 5, 6], stored=6
mine=1, latest=2
```

Hai tập giá trị khác nhau một đơn vị ở đầu và cuối, nhưng cả hai bộ đếm đều kết thúc bằng 6. Tác vụ nào nhận số nào có thể thay đổi giữa các lần chạy. `TreeSet` chỉ được sửa trong `main` sau khi lấy kết quả `Future`, không cần dùng nó như một bộ sưu tập đồng thời.

Dòng cuối minh họa điều quan trọng: biến cục bộ `mine` vẫn giữ kết quả 1 của lần tăng đầu; một luồng khác tăng tiếp nên giá trị dùng chung đã là 2. Kết quả trả về không hứa bộ đếm sẽ đứng yên cho tới khi người gọi dùng xong giá trị đó.

Chương trình chứng minh quy tắc trả kết quả và không mất phép tăng trong trường hợp này; nó không đo hiệu năng, độ công bằng hay thứ tự hoàn tất công việc.

## 5. Hiểu đúng khi có nhiều luồng

Một phép tăng nguyên tử có thể được xem như có một thời điểm hiệu lực duy nhất trong khoảng từ khi gọi đến khi trả về. `getAndIncrement()` trả giá trị ngay trước lần tăng đó; `incrementAndGet()` trả giá trị ngay sau lần tăng đó.

Tuy nhiên, một lời gọi có thể bị tạm dừng trước khi người gọi nhận được quyền chạy tiếp. Trong khoảng ấy, luồng khác có thể đã thực hiện nhiều lần tăng nữa. Vì vậy, các khẳng định sau khác nhau:

- “Tôi nhận số 7 từ lần tăng của mình”: có thể dựa trên giá trị trả về.
- “Hiện tại bộ đếm chắc chắn còn là 7”: không được bảo đảm nếu vẫn có người ghi.
- “Việc mang số 7 chắc chắn hoàn tất trước việc mang số 8”: không được suy ra từ thứ tự cấp số.

Nếu mỗi lời gọi cần một số riêng, hãy giữ giá trị trả về trong biến cục bộ và dùng chính nó. Đừng lấy một số rồi dùng `counter.get()` về sau như thể đó vẫn là số được cấp cho lần gọi ban đầu.

Các phương thức tương ứng của `AtomicLong` có quy tắc trả trước/sau giống nhau, chỉ khác kiểu kết quả `long`. Xem [AtomicLong](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html).

## 6. Lỗi lệch một đơn vị và giới hạn nguyên tử

### Khởi tạo sai so với quy ước

Muốn các chỉ số 0, 1, 2… nhưng khởi tạo 0 rồi dùng `incrementAndGet()` sẽ bắt đầu từ 1. Muốn lần cấp đầu là 1 nhưng khởi tạo 1 rồi dùng `incrementAndGet()` sẽ bắt đầu từ 2. Hãy viết ra hai lần gọi đầu tiên trên giấy để kiểm tra cả giá trị trả về lẫn giá trị lưu.

### Kiểm tra giới hạn rồi tăng tách rời

Mã minh họa sau không bảo đảm chỉ cấp chỉ số trong giới hạn:

```java
if (index.get() < size) {
    int assigned = index.getAndIncrement();
    use(assigned);
}
```

Nhiều luồng có thể cùng vượt qua phép kiểm tra. Sử dụng `getAndIncrement()` làm nguyên tử lần cấp số, nhưng không gộp cả phép kiểm tra `index.get() < size` vào lần cấp đó. Khi cần bảo đảm không vượt sức chứa, thiết kế một phép cập nhật có điều kiện hoặc dùng cơ chế đồng bộ bao phủ toàn bộ quyết định.

### Nghĩ rằng tăng nguyên tử tránh tràn

Cả hai phương thức vẫn tuân theo phép toán của `int` hoặc `long`. Ví dụ một `AtomicInteger` tại `Integer.MAX_VALUE`:

| Phương thức | Kết quả trả về | Giá trị lưu sau đó |
| --- | --- | --- |
| `getAndIncrement()` | `2147483647` | `-2147483648` |
| `incrementAndGet()` | `-2147483648` | `-2147483648` |

Bảng dùng hai bộ đếm độc lập cùng khởi tạo ở giá trị cực đại. Nếu dùng số để nhận diện duy nhất, cần xét cả việc tràn, đặt lại bộ đếm và vòng đời tiến trình; một phép tăng nguyên tử không tự giải quyết những yêu cầu đó.

## 7. Tự kiểm tra nhanh

1. Bộ đếm đang là 20, gọi `getAndIncrement()` trả gì? **20**, sau phép tăng lưu 21 nếu chưa có cập nhật tiếp.
2. Một bộ đếm khác cũng đang 20, gọi `incrementAndGet()` trả gì? **21**.
3. Muốn cấp số đầu tiên bằng 500 bằng `getAndIncrement()`, khởi tạo bao nhiêu? **500**.
4. Nhận 21 từ `incrementAndGet()` rồi gọi `get()` có chắc vẫn là 21? **Không**, một luồng khác có thể đã cập nhật.
5. Hai phương thức có làm phép tăng nguyên tử như nhau không? **Có**, khác biệt cần chọn ở đây là kết quả trước hay sau lần tăng.
