# Giới hạn của hàm tính toán: cập nhật đệ quy và tác vụ kéo dài

## 1. Hiểu vai trò của callback trước khi đặt công việc vào map

Trong nhóm Map và Set đồng thời, một nhu cầu thường gặp là: nhiều luồng cùng gặp một khóa chưa có dữ liệu, hoặc cùng muốn thay đổi giá trị hiện có. Nếu tự viết chuỗi “đọc → kiểm tra → ghi”, hai luồng có thể cùng quyết định dựa trên một trạng thái đã cũ. Các phương thức như `computeIfAbsent`, `computeIfPresent`, `compute` và `merge` cho phép mô tả phép tính cần thực hiện ngay tại điểm cập nhật.

Hàm được truyền vào phương thức đó gọi là hàm gọi lại (callback). Với `computeIfAbsent`, nó thường tạo giá trị cho khóa còn thiếu. Với `compute`, nó nhận khóa và giá trị cũ, rồi quyết định giá trị mới. Nhìn bên ngoài, lời gọi rất gọn:

```java
// Mã minh họa trong một phương thức; chưa phải chương trình độc lập.
counts.compute("java", (key, oldCount) ->
        oldCount == null ? 1 : oldCount + 1);
```

Callback này chỉ tính một số nguyên rồi trả về. Map phụ trách công bố kết quả. Cách phân công đó giúp người đọc thấy rõ phần nào thuộc phép tính và phần nào thuộc cơ chế cập nhật.

Khó khăn xuất hiện khi thay phép cộng bằng công việc có vòng phụ thuộc hoặc thời gian không kiểm soát: tải từ máy chủ, đọc cơ sở dữ liệu, chờ một tác vụ khác, gọi một hàm tiện ích quay lại sửa chính map. Một dòng lambda vẫn có thể chứa cả một quy trình dài.

Bài này tập trung vào `ConcurrentHashMap` trên Java 17 trở lên. Cần phân biệt ba lớp:

- **Phép cập nhật:** thay đổi liên kết giữa một khóa và giá trị.
- **Công việc của ứng dụng:** tải dữ liệu, kiểm tra điều kiện, tính toán nghiệp vụ.
- **Quan hệ chờ:** luồng nào cần kết quả của luồng nào, tài nguyên nào đang bị giữ trong lúc chờ.

Tính an toàn khi nhiều luồng truy cập map không tự thiết kế thay hai lớp còn lại. Sau bài học, người học cần giải thích được vì sao callback nên ngắn, nhận ra cập nhật đệ quy dù đi qua nhiều hàm, và chọn cách đưa tác vụ chậm ra ngoài phép cập nhật mà vẫn hiểu chi phí tải trùng hoặc dùng chung kết quả.

Các chương trình bên dưới độc lập với nhau. Lưu mỗi chương trình vào đúng tên tệp ghi trong mục tương ứng, dùng JDK 17 hoặc mới hơn và chạy từ thư mục chứa tệp. Lệnh `--release 17` giữ mã trong phạm vi API và cú pháp Java 17. Kết quả chỉ in từ luồng chính sau những điểm phối hợp cần thiết, tránh suy luận từ thứ tự in ngẫu nhiên giữa các luồng.

## 2. Đọc đúng phạm vi bảo đảm

Với `ConcurrentHashMap`, lời gọi tính toán có tính nguyên tử đối với cập nhật liên quan. Callback của `computeIfAbsent` chạy khi cần tạo giá trị; callback của `computeIfPresent` chạy khi khóa có giá trị; `compute` tính cho cả trường hợp thiếu khóa. Callback phải ngắn, đơn giản và không sửa chính map đang tính. Một số cập nhật khác có thể phải chờ. Cập nhật đệ quy bị phát hiện có thể dẫn đến `IllegalStateException`. Xem [hợp đồng của ConcurrentHashMap trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function)).

“Tính nguyên tử” cần được đặt cạnh đúng đối tượng được thay đổi. Giả sử callback gửi thư rồi trả về một giá trị: việc cài giá trị vào map và việc thư đã được gửi là hai sự kiện riêng. Nếu sau khi gửi thư callback ném lỗi, ứng dụng cần tự giải quyết hậu quả của thư đó. Không có căn cứ để xem toàn bộ hàm như một giao dịch của cơ sở dữ liệu.

Tương tự, một lời gọi không làm cho một chuỗi lời gọi trở thành một hành động duy nhất. Nếu nghiệp vụ phải chuyển số lượng từ khóa A sang khóa B, hai phép `compute` rời nhau chưa thể hiện một ranh giới giao dịch chung. Cần một thiết kế phối hợp ở mức nghiệp vụ; nhét phép cập nhật B vào callback A sẽ tạo thêm vấn đề.

### Bốn dạng hàm cần nhận diện

| Phương thức | Dữ liệu callback nhận | Quyết định mà callback thể hiện |
|---|---|---|
| `computeIfAbsent(k, f)` | Khóa đang thiếu | Tạo giá trị để dùng cho khóa đó |
| `computeIfPresent(k, f)` | Khóa và giá trị hiện có | Thay đổi hoặc bỏ liên kết hiện có |
| `compute(k, f)` | Khóa và giá trị cũ, có thể thiếu | Quyết định liên kết tiếp theo |
| `merge(k, value, f)` | Giá trị cũ và giá trị đầu vào khi phải gộp | Gộp hai giá trị thành kết quả tiếp theo |

Bảng giúp đọc mã, không phải lời mời đưa thêm thao tác cập nhật vào callback. “Quyết định liên kết tiếp theo” nghĩa là **trả kết quả cho phương thức đang gọi**, thay vì tự gọi `put`, `remove` hoặc `compute` để can thiệp vào cùng map trong lúc phương thức đó còn chạy.

Cũng cần kiểm tra lớp triển khai thực tế. Một biến có kiểu `ConcurrentMap` có thể trỏ đến nhiều lớp khác nhau. Các cài đặt mặc định của giao diện này có thể thử lại, khiến hàm tính lại được gọi nhiều lần trong tranh chấp. Không suy rộng đặc tính của `ConcurrentHashMap` cho mọi lớp triển khai. Xem [phần Implementation Requirements của ConcurrentMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#compute(K,java.util.function.BiFunction)).

Từ đó có một nguyên tắc thiết kế dễ áp dụng: callback chủ yếu biến dữ liệu đầu vào thành kết quả. Càng ít tác động bên ngoài, mã càng dễ xem xét khi thay lớp triển khai, thêm cơ chế thử lại hoặc xử lý lỗi.

## 3. Giá trị null, ngoại lệ và số lần thực hiện công việc

Trong các phép tính của `Map`, kết quả `null` được dùng để quyết định không tạo hoặc bỏ liên kết, tùy phương thức. Callback ném ngoại lệ không có nghĩa ứng dụng nhận lại một giá trị mặc định. Cần đọc đúng nhánh trả về và nhánh lỗi. Xem [hợp đồng compute của Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#compute(K,java.util.function.BiFunction)).

### Chương trình: kết quả của một callback và tác động đã xảy ra

Tệp `ComputeOutcomesDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class ComputeOutcomesDemo {
    public static void main(String[] args) {
        var values = new ConcurrentHashMap<String, Integer>();
        var attempts = new AtomicInteger();

        values.put("ready", 10);
        int ready = values.computeIfAbsent("ready", key -> {
            attempts.incrementAndGet();
            return 99;
        });
        System.out.println("ready=" + ready + ", attempts=" + attempts.get());

        values.computeIfAbsent("missing", key -> {
            attempts.incrementAndGet();
            return null;
        });
        values.computeIfAbsent("missing", key -> {
            attempts.incrementAndGet();
            return null;
        });
        System.out.println("missingPresent=" + values.containsKey("missing"));
        System.out.println("attemptsAfterNull=" + attempts.get());

        try {
            values.compute("ready", (key, oldValue) -> {
                attempts.incrementAndGet();
                throw new IllegalArgumentException("invalid input");
            });
        } catch (IllegalArgumentException ex) {
            System.out.println("failure=" + ex.getClass().getSimpleName());
        }
        System.out.println("readyAfterFailure=" + values.get("ready"));
        System.out.println("attemptsAfterFailure=" + attempts.get());

        int updated = values.compute("ready", (key, oldValue) -> oldValue + 5);
        System.out.println("updated=" + updated);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ComputeOutcomesDemo.java
java ComputeOutcomesDemo
```

Stdout:

```text
ready=10, attempts=0
missingPresent=false
attemptsAfterNull=2
failure=IllegalArgumentException
readyAfterFailure=10
attemptsAfterFailure=3
updated=15
```

Có bốn quan sát trong chương trình:

1. Khóa `ready` đã tồn tại. Lambda tạo giá trị không chạy trong lời gọi đầu, nên `attempts` vẫn bằng 0.
2. Hai lời gọi cho `missing` đều trả `null`. Không có kết quả được giữ lại để dùng cho lần sau, nên bộ đếm tăng hai lần.
3. Callback cho `ready` tăng bộ đếm rồi ném lỗi. Liên kết vẫn trỏ đến số 10, còn bộ đếm đã là 3.
4. Phép cộng cuối không có tác động phụ; nó trả 15 để cập nhật.

Bộ đếm là dụng cụ quan sát của thí nghiệm. Trong mã nghiệp vụ, thay bộ đếm bằng một khoản trừ tiền hoặc yêu cầu gửi ra ngoài sẽ khiến cùng trình tự trở nên nghiêm trọng hơn. Phép tính thất bại không tự thu hồi một hành động đã hoàn tất trước đó.

### “Một lần” cần gắn với phạm vi cụ thể

Cần tách các câu hỏi:

- Callback có chạy trong **lời gọi hiện tại** không?
- Các lời gọi khác có thể cần tính lại sau `null`, ngoại lệ hoặc xóa khóa không?
- Có bao nhiêu ứng viên được tạo trước khi một giá trị được giữ lại?
- Có tác động bên ngoài nào đã xảy ra trong các lần tính đó?

Ví dụ trên tự tạo hai lời gọi riêng cho `missing`; không có mâu thuẫn khi hàm tạo dữ liệu thực hiện hai lần. Nếu một dịch vụ trả `null` vì “không tìm thấy”, việc lặp lại yêu cầu có thể là chính sách mong muốn hoặc là một lỗi thiết kế bộ nhớ đệm. Muốn lưu cả kết quả “không tìm thấy”, hãy biểu diễn nó bằng một giá trị rõ ràng và quyết định thời hạn giữ kết quả ấy.

Không nên diễn giải chữ “nguyên tử” thành cam kết chỉ tải dữ liệu đúng một lần trong suốt vòng đời chương trình. Vòng đời khóa, chính sách xóa và chính sách xử lý lỗi vẫn do ứng dụng quyết định.

## 4. Cập nhật đệ quy: hàm tính toán quay lại nơi đang được tính

Đệ quy trong ngữ cảnh này không chỉ là một phương thức Java tự gọi chính nó. Điều cần tìm là **đường gọi quay lại cập nhật map khi callback trước chưa kết thúc**.

### 4.1. Cùng khóa, cùng map

Hãy xét chuỗi phụ thuộc:

```text
Cần tạo giá trị cho A
    → callback của A chạy
        → lại yêu cầu tạo giá trị cho A
            → giá trị A đầu tiên chưa thể được trả về
```

Lời gọi bên trong cần hoàn thành phần việc mà chính lời gọi bên ngoài đang thực hiện. Thêm `synchronized` quanh lambda không làm xuất hiện giá trị còn thiếu. Vấn đề nằm ở quan hệ phụ thuộc.

Chương trình sau cố ý vi phạm giới hạn để quan sát lỗi, không phải mẫu cài đặt bộ nhớ đệm. Nó dùng một map mới, một khóa và một luồng; người học không cần chạy cuộc đua giữa các luồng để thấy vấn đề.

Tệp `RecursiveUpdateDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class RecursiveUpdateDemo {
    public static void main(String[] args) {
        var values = new ConcurrentHashMap<String, Integer>();
        try {
            values.computeIfAbsent("A", key ->
                    values.computeIfAbsent("A", nestedKey -> 42));
            System.out.println("unexpected success");
        } catch (IllegalStateException ex) {
            System.out.println("failure=" + ex.getClass().getSimpleName());
        }
        System.out.println("containsA=" + values.containsKey("A"));
        System.out.println("size=" + values.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 RecursiveUpdateDemo.java
java RecursiveUpdateDemo
```

Stdout:

```text
failure=IllegalStateException
containsA=false
size=0
```

Trên JDK 17 dùng để kiểm chứng bài, lời gọi bị phát hiện và ném `IllegalStateException`; không có liên kết A được tạo. Không phụ thuộc vào thông điệp lỗi cụ thể vì nội dung thông điệp không phải điều cần dùng để quyết định nghiệp vụ.

**Không lấy việc có hoặc không có ngoại lệ làm phép kiểm tra hợp lệ của thiết kế.** Chương trình này chứng minh một trường hợp bị phát hiện. Nó không chứng minh mọi đường gọi đệ quy, mọi sơ đồ khóa và mọi phiên bản JVM đều được chẩn đoán theo cùng một cách.

### 4.2. Khác khóa vẫn phải xem đường gọi

Một cách “sửa” dễ gặp là đổi lời gọi bên trong sang B:

```java
// Mã minh họa SAI; không chạy như một giải pháp.
cache.computeIfAbsent("A", key ->
        cache.computeIfAbsent("B", otherKey -> "value"));
```

Việc tên khóa khác nhau chưa loại bỏ thao tác sửa cùng map trong callback. Có thể dữ liệu thử hiện tại chạy qua, rồi thay phân bố băm hoặc thêm một nhánh tải dữ liệu sẽ làm lộ vấn đề. Hãy bỏ đường cập nhật lồng nhau, thay vì tìm một cặp khóa làm đoạn mã tình cờ chạy được.

Nếu A cần thông tin B để được xây dựng, hãy quyết định ở tầng tính toán: tính các phụ thuộc ngoài callback, truyền vào một kết quả đã sẵn sàng, hoặc tổ chức quy trình có quản lý quan hệ phụ thuộc. Khi kết quả đã đủ, bước công bố vào map mới diễn ra.

### 4.3. Hàm tiện ích có thể che giấu vòng gọi

Xét đoạn minh họa chưa phải chương trình độc lập:

```java
// Mã minh họa SAI: phải đọc cả đường gọi của load().
Value value = cache.computeIfAbsent(key, this::load);

// Nếu load() hoặc hàm mà nó gọi lại sửa cache,
// giới hạn vẫn bị vi phạm dù lambda không chứa tên cache.
```

Khi xem xét `load`, không chỉ tìm một lời gọi trực tiếp. Hàm dựng đối tượng, bộ phân giải phụ thuộc, mã mở rộng do người dùng cung cấp hoặc hàm ghi nhận sự kiện đều có thể gọi ngược vào dịch vụ đang dùng map.

Một câu hỏi thực tế là: “Trước khi callback trả về, bất kỳ đoạn mã nào trên đường gọi có thể yêu cầu tạo hoặc sửa một mục của cùng kho dữ liệu không?” Nếu không xác định được, cần thu hẹp trách nhiệm của callback.

### 4.4. Hai map khác nhau cũng có thể tạo vòng chờ

Giới hạn sửa chính map không phải công cụ phát hiện mọi bế tắc của ứng dụng. Hãy tưởng tượng:

```text
Luồng 1: đang tính mục của map M → cần công việc ở map N
Luồng 2: đang tính mục của map N → cần công việc ở map M
```

Ngay cả khi mỗi hàm chỉ nhìn thấy một lời gọi “sang map khác”, tổng thể có thể tạo vòng phụ thuộc. Cần xem thứ tự lấy tài nguyên, đường chờ và dữ liệu phụ thuộc trong toàn bộ quy trình.

Vì vậy, quy tắc thực dụng là tách phép biến đổi cục bộ khỏi việc điều phối quy trình. Callback càng phải biết về nhiều dịch vụ, nhiều khóa và nhiều nguồn dữ liệu thì càng khó chứng minh nó kết thúc được.

## 5. Tác vụ kéo dài: tính đúng kết quả chưa đủ để có khả năng tiến triển

Một callback không đệ quy vẫn có thể gây rắc rối nếu giữ công việc cập nhật quá lâu. Ví dụ:

- Chờ kết nối hoặc phản hồi HTTP.
- Đọc tệp, truy vấn cơ sở dữ liệu, đợi một khóa ngoài.
- Tính toán tốn CPU trên dữ liệu lớn.
- Gọi `get()` hoặc `join()` cho một tác vụ chưa hoàn tất.
- Thực hiện vòng thử lại không có giới hạn kết thúc rõ ràng.

“Ngắn” không có một con số mili giây chung cho mọi hệ thống. Hãy xét công việc có được chặn trên tài nguyên bên ngoài hay không, khối lượng có bị giới hạn hay không và bao nhiêu yêu cầu có thể phải chờ nó.

Trong cài đặt OpenJDK 17, các mục được tổ chức theo vùng băm và một số cập nhật phối hợp bằng khóa theo vùng. Hàm tính lâu có thể trì hoãn cập nhật của mục khác trong cùng vùng; không nên xem mỗi khóa như có một cơ chế chờ hoàn toàn tách biệt. Đây là giải thích về cài đặt, không phải giao diện khóa để ứng dụng dựa vào. Xem [chú thích thiết kế ConcurrentHashMap của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/concurrent/ConcurrentHashMap.java).

### 5.1. Quan sát lúc giá trị chưa được công bố

Thí nghiệm tiếp theo cố ý giữ callback ở một cổng chờ để quan sát trạng thái. Đây là dụng cụ học, không phải mẫu nên đặt vào callback thật. Nó không dùng `Thread.sleep` để đoán một luồng đã chạy đến đâu.

Tệp `WaitingComputeDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class WaitingComputeDemo {
    public static void main(String[] args) throws Exception {
        var values = new ConcurrentHashMap<String, String>();
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(2);

        try {
            var first = pool.submit(() ->
                    values.computeIfAbsent("A", key -> {
                        entered.countDown();
                        try {
                            if (!release.await(10, TimeUnit.SECONDS)) {
                                throw new IllegalStateException("release timeout");
                            }
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                        return "first";
                    }));

            if (!entered.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("entry timeout");
            }
            System.out.println("getWhileComputing=" + values.get("A"));

            var second = pool.submit(() -> values.put("A", "second"));
            release.countDown();

            System.out.println("firstResult=" + first.get(10, TimeUnit.SECONDS));
            System.out.println("secondPrevious=" + second.get(10, TimeUnit.SECONDS));
            System.out.println("finalValue=" + values.get("A"));
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 WaitingComputeDemo.java
java WaitingComputeDemo
```

Stdout:

```text
getWhileComputing=null
firstResult=first
secondPrevious=first
finalValue=second
```

Cổng `entered` cho biết callback đầu đã bắt đầu. Cổng `release` được giữ lại đến sau khi luồng chính gọi `get("A")`. Lúc đó kết quả `"first"` chưa được callback trả ra, vì vậy phép đọc chưa nhận được liên kết A.

Sau khi mở cổng, lời gọi đầu trả `"first"`; phép `put` sau nhận giá trị trước đó là `"first"`, rồi map chứa `"second"`.

Giới hạn quan sát cần nói rõ:

- Chương trình không in thời gian, không đo độ trễ trung bình hay tối đa.
- Việc đã `submit` tác vụ thứ hai không chứng minh nó lập tức được CPU thực thi.
- Giá trị timeout 10 giây dùng để phát hiện thí nghiệm không tiến triển trong môi trường chạy; đó không phải giới hạn thời gian của API.
- Thứ tự công bố dữ liệu được kiểm soát bởi cổng chờ và việc lấy kết quả, không phải bởi tốc độ của máy.
- Một lần chạy thành công không kiểm tra hết lịch thực thi có thể có của chương trình khác.

Phép đọc trả `null` cũng không phải một tín hiệu ứng dụng có thể dùng để khẳng định “không ai đang tính A”. Nó chỉ là giá trị của phép đọc đó. Nếu nghiệp vụ cần phân biệt thiếu dữ liệu với đang tải, mô hình dữ liệu phải biểu diễn trạng thái đang tải.

### 5.2. Chờ vòng ngoài có thể khiến mọi thứ dừng lại

Xét tình huống thiết kế, không phải đoạn mã để chạy:

```text
Callback A chờ kết quả của tác vụ T
T cần cập nhật A trước khi hoàn tất
Callback A chỉ kết thúc sau khi T hoàn tất
```

Chuyển T sang một `ExecutorService` không tự phá vòng phụ thuộc. Nếu callback gọi `future.get()` ngay sau khi gửi T, quan hệ chờ vẫn tồn tại.

Có một dạng khác ở tầng bộ thực thi: tất cả luồng trong một nhóm đều đang chờ các tác vụ mới được xếp vào chính nhóm đó. Khi không còn luồng rảnh để thực hiện các tác vụ mới, công việc có thể không tiến triển. Map đồng thời không giải quyết việc cấp phát luồng hoặc thứ tự phụ thuộc này.

Trước khi dùng một lời gọi chờ, cần xác định ai có thể hoàn thành công việc được chờ và liệu người đó có cần tài nguyên mà bên chờ đang giữ hay không.

## 6. Cách thứ nhất: tính bên ngoài, công bố bằng putIfAbsent

Khi tạo trùng dữ liệu có thể chấp nhận được, một cách đơn giản là:

```text
Tạo ứng viên ngoài callback
    → cố gắng công bố bằng putIfAbsent
        → nếu có giá trị trước, dùng giá trị trước
        → nếu chưa có, dùng ứng viên vừa công bố
```

Đây là một lựa chọn thiết kế suy ra từ việc tách “tạo ứng viên” và “chọn giá trị được lưu”. Mục tiêu là làm bước cập nhật ngắn và rõ, với chi phí có thể phải tạo ứng viên nhiều lần.

Tệp `OutsideCandidateDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class OutsideCandidateDemo {
    record Data(String text) {}

    public static void main(String[] args) throws Exception {
        var values = new ConcurrentHashMap<String, Data>();
        var candidates = new AtomicInteger();
        var bothCreated = new CyclicBarrier(2);
        var pool = Executors.newFixedThreadPool(2);

        try {
            java.util.concurrent.Callable<Data> request = () -> {
                Data candidate = new Data("loaded");
                candidates.incrementAndGet();
                bothCreated.await(10, TimeUnit.SECONDS);
                Data existing = values.putIfAbsent("A", candidate);
                return existing == null ? candidate : existing;
            };

            var first = pool.submit(request);
            var second = pool.submit(request);
            Data left = first.get(10, TimeUnit.SECONDS);
            Data right = second.get(10, TimeUnit.SECONDS);

            System.out.println("candidates=" + candidates.get());
            System.out.println("samePublishedObject=" + (left == right));
            System.out.println("storedText=" + values.get("A").text());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 OutsideCandidateDemo.java
java OutsideCandidateDemo
```

Stdout:

```text
candidates=2
samePublishedObject=true
storedText=loaded
```

`CyclicBarrier` buộc cả hai tác vụ tạo xong ứng viên trước khi cùng đi đến bước công bố. Bởi vậy số ứng viên luôn là 2 trong thí nghiệm này. Hai đối tượng `Data` độc lập có cùng nội dung `"loaded"`.

Cả hai bên đều trả lại đối tượng đã được chọn cho map. Biểu thức `left == right` kiểm tra cùng tham chiếu, chứ không chỉ so sánh nội dung. Kết quả minh họa rõ: **hai lần tạo ứng viên nhưng một đối tượng được dùng chung**.

### 6.1. Điều phải chấp nhận khi dùng cách này

Nếu công việc ngoài map chỉ đọc một nguồn dữ liệu, việc tải trùng có thể là chi phí chấp nhận được. Nếu đó là một hành động cần tránh lặp, chẳng hạn cấp một tài nguyên bên ngoài có giới hạn, cần thiết kế khác hoặc cơ chế đảm bảo ở hệ thống sở hữu hành động đó.

Nếu ứng viên chứa tài nguyên cần đóng, bên thua cuộc phải giải phóng ứng viên của mình theo đúng hợp đồng tài nguyên. Không đóng đối tượng thắng đang được map và những bên khác sử dụng.

Thí nghiệm dùng khóa chưa có và không có thao tác xóa xen vào. Trong một bộ nhớ đệm thực, “chọn được đối tượng” không có nghĩa nó sẽ nằm trong map mãi mãi. Một luồng khác có thể xóa hoặc thay dữ liệu sau bước công bố. Nếu điều này ảnh hưởng đến nghiệp vụ, cần nêu rõ vòng đời và cách vô hiệu hóa dữ liệu.

### 6.2. Vì sao không dùng put để bước sau cùng thắng?

Nếu các bên đều `put` ứng viên riêng, bên sau có thể thay giá trị bên trước vừa công bố. Khi cần dùng cùng một kết quả cho lần tạo hiện tại, đó là một chính sách khác.

Cách trên chủ ý chọn người công bố đầu và trả cùng đối tượng đó cho các bên đang tranh chấp. Nó không giải quyết “dữ liệu nào mới nhất” nếu mỗi ứng viên đại diện cho một phiên bản khác nhau. Với dữ liệu có phiên bản, bước chọn phải xét phiên bản hoặc một quy tắc nghiệp vụ được định nghĩa rõ.

## 7. Cách thứ hai: công bố tác vụ, rồi thực hiện công việc bên ngoài map

Nếu tải trùng là điều cần tránh trong cùng một đợt tải, có thể cho map giữ **đối tượng đại diện kết quả đang được tính**, thay vì chỉ giữ kết quả cuối.

```text
Map: khóa → FutureTask

1. Tìm hoặc công bố một FutureTask còn chưa chạy.
2. Ra khỏi thao tác cập nhật map.
3. Gọi run() trên tác vụ đã được chọn.
4. Lấy kết quả từ chính tác vụ đó.
```

`FutureTask` bọc một `Callable`, giữ kết quả hoặc trạng thái lỗi, và cung cấp `get()` để chờ kết quả. Nó thực hiện một lần tính cho vòng đời thông thường của đối tượng; tạo `FutureTask` không tự khởi chạy công việc. Xem [FutureTask trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html).

Mẫu dưới đây là một bộ nhớ đệm minh họa tối giản, chỉ giữ chuỗi. Hàm tải giống nhau cho mọi khóa để tập trung vào cơ chế phối hợp; ứng dụng thực tế cần truyền khóa vào hàm tải phù hợp.

Tệp `SharedTaskDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SharedTaskDemo {
    static final class Memo {
        private final ConcurrentHashMap<String, FutureTask<String>> tasks =
                new ConcurrentHashMap<>();
        private final Callable<String> loader;

        Memo(Callable<String> loader) {
            this.loader = loader;
        }

        String get(String key) throws InterruptedException, ExecutionException {
            FutureTask<String> task = tasks.get(key);
            if (task == null) {
                FutureTask<String> candidate = new FutureTask<>(loader);
                FutureTask<String> existing = tasks.putIfAbsent(key, candidate);
                task = existing == null ? candidate : existing;
            }

            // Run outside every map callback; concurrent run calls are safe.
            task.run();
            try {
                return task.get();
            } catch (ExecutionException | CancellationException ex) {
                tasks.remove(key, task);
                throw ex;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        var calls = new AtomicInteger();
        var memo = new Memo(() -> {
            calls.incrementAndGet();
            return new String("data");
        });
        var start = new CyclicBarrier(2);
        var pool = Executors.newFixedThreadPool(2);

        try {
            Callable<String> request = () -> {
                start.await(10, TimeUnit.SECONDS);
                return memo.get("A");
            };
            var first = pool.submit(request);
            var second = pool.submit(request);
            String left = first.get(10, TimeUnit.SECONDS);
            String right = second.get(10, TimeUnit.SECONDS);

            System.out.println("loaderCalls=" + calls.get());
            System.out.println("sameResultObject=" + (left == right));
            System.out.println("cachedAgain=" + memo.get("A"));
            System.out.println("loaderCallsAfterHit=" + calls.get());

            var retryCalls = new AtomicInteger();
            var retryMemo = new Memo(() -> {
                if (retryCalls.incrementAndGet() == 1) {
                    throw new IllegalStateException("temporary failure");
                }
                return "recovered";
            });
            try {
                retryMemo.get("B");
            } catch (ExecutionException ex) {
                System.out.println("firstFailure=" +
                        ex.getCause().getClass().getSimpleName());
            }
            System.out.println("retryResult=" + retryMemo.get("B"));
            System.out.println("retryCalls=" + retryCalls.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SharedTaskDemo.java
java SharedTaskDemo
```

Stdout:

```text
loaderCalls=1
sameResultObject=true
cachedAgain=data
loaderCallsAfterHit=1
firstFailure=IllegalStateException
retryResult=recovered
retryCalls=2
```

### 7.1. Theo dõi ai làm việc ở từng bước

`tasks.get(key)` tìm tác vụ đang được giữ. Nếu chưa thấy, bên gọi tạo một ứng viên `FutureTask` rồi dùng `putIfAbsent` để chọn một tác vụ.

Ứng viên ở đây chỉ là đối tượng gói công việc. Việc tạo nó không chạy `loader`. Những ứng viên thua cuộc chưa gây ra các lần tải dữ liệu tương ứng. Đó là khác biệt với việc thực hiện đầy đủ thao tác tải trước `putIfAbsent` ở mục trước.

Sau bước chọn, mọi bên gọi đều dùng biến `task` trỏ đến tác vụ thắng. Chúng cùng có thể gọi `run()`; công việc của đối tượng `FutureTask` ấy vẫn chỉ được thực hiện một lần. Những lời gọi khác tiếp tục lấy cùng kết quả.

**`run()` ở đây chạy đồng bộ trên một luồng gọi phương thức.** Cách viết này giúp một bên khác có thể bắt đầu tác vụ đã công bố nếu bên công bố chưa kịp gọi `run`. Nó không tạo một luồng mới và không phải API bất đồng bộ cho người sử dụng `Memo`.

Cần phân biệt hai vị trí của công việc dài:

- Luồng gọi `Memo.get` vẫn có thể bận hoặc chờ khi tải chậm.
- Luồng đó thực hiện phần dài sau khi ra khỏi thao tác cập nhật map.

Mẫu này xử lý phạm vi công việc bị giữ trong phép cập nhật; nhu cầu giải phóng luồng gọi, giới hạn số tải đồng thời và đáp ứng yêu cầu hủy phải được thiết kế riêng.

### 7.2. Đọc kết quả lỗi và chính sách thử lại

Trong phần thử lại, lần tải đầu ném `IllegalStateException`. Người gọi `get()` nhận `ExecutionException` chứa nguyên nhân đó. Chương trình in tên lớp nguyên nhân, xóa đúng tác vụ lỗi, rồi lời gọi tiếp theo tạo tác vụ khác và nhận `"recovered"`.

Khi lấy thành công kết quả bằng `Future.get()`, các hành động trong công việc tính toán có quan hệ happens-before với hành động sau `get()` ở luồng nhận. `get()` cũng phân biệt lỗi tính toán, gián đoạn và hủy. Xem [hợp đồng Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html#get()).

Như vậy, trong mô hình này có hai thời điểm riêng: công bố đối tượng tác vụ vào map và hoàn tất kết quả mà tác vụ đại diện. Nhìn thấy tác vụ chưa có nghĩa kết quả đã sẵn sàng.

Xóa tác vụ lỗi là **chính sách của ví dụ**, không phải yêu cầu mọi bộ nhớ đệm phải làm. Có hệ thống muốn giữ lỗi một khoảng thời gian để tránh làm quá tải nguồn đang gặp sự cố. Có hệ thống cho phép thử lại với khoảng chờ tăng dần. Dù chọn cách nào, cần nói rõ khi nào một đợt tải kết thúc và đợt tiếp theo được phép bắt đầu.

### 7.3. Vì sao phải remove(key, task)?

Hãy đặt tên tác vụ lỗi cũ là F1, tác vụ mới là F2:

```text
Bên A nhận lỗi của F1 và xóa F1
Bên B tạo, công bố F2 cho cùng khóa
Bên C cũng vừa nhận lỗi của F1 và cần dọn dẹp
```

Nếu C gọi `remove(key)`, nó có thể xóa nhầm F2. Câu lệnh `remove(key, task)` chỉ dọn liên kết còn trỏ đến tác vụ đang được xử lý. Với các đối tượng `FutureTask` của ví dụ, đây chính là kiểm tra đối tượng mong đợi.

Lập luận này cũng dùng được với nhiều dạng công việc có trạng thái: việc dọn một phiên cũ phải có dấu hiệu nhận diện phiên đó. Không nên xóa vô điều kiện chỉ vì khóa có cùng tên.

### 7.4. Những giới hạn được giữ rõ trong mẫu

Mẫu chưa có thời hạn hết hiệu lực, dung lượng tối đa hay cơ chế tự dọn các kết quả thành công. Nếu số khóa tăng mãi, số tác vụ được giữ cũng tăng theo. Muốn dùng trong một ứng dụng lâu dài phải chọn chính sách vòng đời.

Mẫu không công khai phương thức hủy tác vụ. Một người chờ bị gián đoạn không tự xóa tác vụ dùng chung, vì những người khác vẫn có thể cần nó. Nếu thiết kế thêm hủy, phải quyết định ai có quyền hủy phần việc chung và khi nào nó có thể bị loại khỏi map.

Nếu `loader` trả `null`, kết quả đó nằm bên trong `FutureTask`; giá trị của map vẫn là một đối tượng tác vụ. Đây là một tình huống khác với callback của `computeIfAbsent` trả `null`. Cần quyết định riêng việc có giữ kết quả tải rỗng hay không.

Cuối cùng, mẫu giả định các hàm tải không gọi ngược để chờ chính công việc đang được chúng thực hiện. Nếu khi tải A lại gọi `memo.get("A")`, nó có thể chờ chính tác vụ A. Nếu A đợi B và B đợi A, vòng chờ vẫn tồn tại dù không còn callback map nào bao quanh phần tải.

Công bố một `FutureTask` giúp biểu diễn trạng thái đang tải; nó không tự chứng minh đồ thị phụ thuộc không có chu trình.

## 8. Vì sao chỉ thêm CompletableFuture chưa đủ?

Một cách viết trông có vẻ nhanh là trả về một `CompletableFuture` từ callback. Cần xem cả cách tạo, lịch thực thi và vị trí đặt mã xử lý hoàn tất.

Ví dụ sau chỉ minh họa một ý tưởng cần phân tích, chưa phải chương trình độc lập:

```java
// Mã minh họa cần xem xét kỹ đường thực thi.
CompletableFuture<Value> future = cache.computeIfAbsent(key, k ->
        CompletableFuture.supplyAsync(() -> load(k), executor));
```

Có ba việc khác nhau trong đoạn ngắn đó: callback chạy, tác vụ được gửi vào bộ thực thi, và tác vụ tải thực sự được chạy. Không nên gom chúng thành một mốc duy nhất là “đã tải xong”.

Đặc biệt, các bước xử lý hoàn tất không có hậu tố `Async` có thể chạy ngay trên luồng hoàn tất hoặc luồng tham gia hoàn tất. `CompletableFuture` cũng không trực tiếp điều khiển công việc đã tạo kết quả để đảm bảo hủy là dừng I/O. Xem [chính sách thực thi và hủy của CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

Từ các chính sách này, cần kiểm tra những đường gọi cụ thể:

- Bộ thực thi được truyền vào có thể chạy lệnh ngay trên luồng gọi không?
- Chính sách khi hết khả năng nhận việc có chạy công việc trên bên gửi không?
- Tác vụ có thể hoàn tất trước khi callback đang tạo nó trả về không?
- Mã dọn kết quả lỗi có gọi lại `cache.remove` trong chính callback đang còn hoạt động không?
- Có đoạn nào gọi `join()` ngay trong callback, biến phần đã đưa đi thành một chỗ chờ không?

Một thiết kế dễ xem xét hơn là công bố một đối tượng đại diện công việc trước, kết thúc thao tác map, rồi khởi chạy và gắn phần xử lý vòng đời bên ngoài vùng đó. Đây là hướng thiết kế; chi tiết phải giải quyết cả việc bộ thực thi từ chối nhận việc, tác vụ lỗi và các bên cùng dọn dẹp.

Nếu việc gửi tác vụ thất bại mà một future còn chờ mãi trong map, những người đến sau sẽ nhận một đối tượng không ai có thể hoàn tất. Phải hoàn tất nó bằng trạng thái lỗi hoặc dọn đúng đối tượng theo chính sách đã chọn.

Tương tự, giới hạn thời gian của một người chờ không đồng nghĩa nguồn dữ liệu đã dừng. Đừng xóa vô điều kiện phần việc chung chỉ vì một yêu cầu không còn chờ được; một đợt tải mới có thể bắt đầu trong khi đợt cũ vẫn chạy.

## 9. Cách tìm lỗi trong mã đang có

Khi thấy một luồng chậm ở `compute` hoặc `computeIfAbsent`, hãy xem cả đường gọi của callback và nơi nó đang chờ. Chỉ nhìn tên map hoặc việc lớp có chữ “Concurrent” chưa đủ để quyết định nguyên nhân.

### 9.1. Dấu hiệu và hướng kiểm tra

| Dấu hiệu | Điều cần kiểm tra | Hướng thay đổi có căn cứ |
|---|---|---|
| Có `IllegalStateException` khi tạo giá trị | Callback có quay lại sửa cùng map trực tiếp hoặc qua hàm khác không? | Tách xây dựng dữ liệu khỏi công bố |
| Nhiều cập nhật cùng chậm khi tải một dữ liệu | Callback có I/O, tính toán lớn hoặc chờ tác vụ khác không? | Đưa phần dài ra ngoài thao tác cập nhật |
| Tải dữ liệu nhiều lần | Có `null`, lỗi, xóa khóa hoặc nhiều ứng viên tính bên ngoài không? | Định nghĩa vòng đời và chọn cách phối hợp phù hợp |
| Chờ future không kết thúc | Ai thực sự bắt đầu và ai hoàn tất tác vụ? Có vòng phụ thuộc không? | Sửa quan hệ chờ và xử lý cả lỗi gửi tác vụ |
| Tác vụ mới biến mất sau lỗi cũ | Có dọn dẹp bằng `remove(key)` không? | Dọn có điều kiện theo đúng đối tượng tác vụ |
| Liên kết giữ nguyên nhưng dữ liệu con đã đổi | Callback có sửa trực tiếp đối tượng cũ trước khi ném lỗi không? | Tạo kết quả mới hoặc dùng cơ chế quản lý trạng thái riêng |

Cột cuối là hướng kiểm tra thiết kế, không phải một công thức sửa mọi lỗi. Ví dụ, việc tạo một kết quả mới có thể rất tốn kém nếu giá trị là một tập dữ liệu lớn; khi đó cần thiết kế cấu trúc và ranh giới đồng bộ phù hợp thay vì sao chép máy móc.

### 9.2. Phân biệt liên kết và đối tượng được liên kết

Xét đoạn minh họa cố ý có vấn đề, chưa phải chương trình độc lập:

```java
// Mã minh họa SAI: oldList là đối tượng có thể đang được chia sẻ.
cache.compute(key, (k, oldList) -> {
    oldList.add("new");
    throw new IllegalStateException("failed");
});
```

Nếu map vốn trỏ đến `oldList`, việc liên kết không bị thay thế chưa làm phần tử vừa thêm biến mất. Đối tượng được trỏ đến đã bị sửa. Từ đó cũng không thể suy ra các luồng khác được phép sửa hoặc đọc một `ArrayList` chia sẻ tùy ý chỉ vì nó nằm trong map đồng thời.

Trong một thiết kế dùng giá trị bất biến, callback có thể xây một giá trị mới từ giá trị cũ rồi trả nó về sau khi kiểm tra hoàn tất. Cần hiểu chi phí sao chép và độ sâu bất biến; một lớp bao ngoài không tự làm dữ liệu con bất biến.

### 9.3. Dữ liệu quan sát nên tách thời gian chờ và thời gian làm

Khi phân tích hệ thống thật, phân biệt:

- Thời gian tìm hoặc công bố mục trong map.
- Thời gian đợi một đợt tải đã có.
- Thời gian tải ở nguồn dữ liệu.
- Số ứng viên bị bỏ, số lần thử lại và số tác vụ đang chờ.
- Lỗi do dữ liệu, do nguồn tạm thời không đáp ứng và do không nhận được luồng thực thi.

Đừng thêm một thao tác ghi nhật ký chặn lâu vào callback chỉ để đo callback. Có thể lấy thời gian ở ranh giới ngoài, giữ dữ liệu đo cục bộ và xử lý phần ghi nhận theo một thiết kế không làm trầm trọng hơn chỗ nghẽn đang tìm.

Với bế tắc, ảnh chụp trạng thái luồng và đường chờ hữu ích hơn một phép đo tổng thời gian duy nhất. Với chậm do tải cao, cần biết phân bố khóa, số lần tải đồng thời và hàng chờ. Các thí nghiệm nhỏ trong bài giúp hiểu cơ chế, không thay thế phép đo ứng dụng cụ thể.

## 10. Thực hành và tự kiểm tra thiết kế

### Bài 1: nhận diện cập nhật đệ quy bị giấu

Một hàm `getProduct(id)` gọi `computeIfAbsent`. Callback gọi `buildProduct(id)`; hàm dựng này gọi `getProduct(parentId)` để lấy sản phẩm cha.

Hãy trả lời:

1. Việc `parentId` khác `id` đã đủ chứng minh an toàn chưa?
2. Nếu quan hệ cha tạo chu trình A → B → A thì bên nào có thể hoàn tất trước?
3. Nếu không có chu trình dữ liệu, việc sửa cùng map trong callback đã được loại bỏ chưa?

Hướng giải thích: khóa khác chưa cho phép cập nhật lồng trong cùng map. Chu trình phụ thuộc cần được phát hiện ở tầng mô hình hoặc quy trình tải. Có thể xây dựng các phụ thuộc ngoài callback rồi công bố kết quả, hoặc dùng một cơ chế tải có quản lý đồ thị phụ thuộc rõ ràng.

### Bài 2: quyết định có chấp nhận tạo ứng viên trùng không

Một thao tác đọc cấu hình mất nhiều thời gian nhưng không có tác động thay đổi nguồn. Hai bên tải trùng rồi chỉ giữ một kết quả có thể chấp nhận được. Hãy chọn cách tính ngoài map rồi `putIfAbsent`, và nêu chi phí tài nguyên bị lặp.

Sau đó thay thao tác đọc bằng việc cấp một mã duy nhất từ hệ thống ngoài. Cần giải thích vì sao “map chỉ giữ một giá trị” không thu hồi mã đã cấp cho ứng viên thua. Nếu hành động cần tránh lặp trên nhiều tiến trình hoặc nhiều máy, cơ chế phối hợp trong một đối tượng map của một JVM không đủ; phải có bảo đảm ở ranh giới hệ thống sở hữu hành động.

### Bài 3: chính sách dọn lỗi và quyền hủy

Với mẫu `SharedTaskDemo`, giả sử hai bên đang chờ F1. Một bên nhận lỗi và xóa F1; sau đó một bên khác công bố F2.

- Nếu bên còn lại của F1 dọn bằng `remove(key)`, điều gì có thể xảy ra?
- Vì sao `remove(key, F1)` giữ được F2?
- Nếu một người dùng ngừng chờ nhưng F1 chưa hoàn tất, có nên hủy phần việc của tất cả mọi người không?

Hướng giải thích: dọn dẹp phải gắn với đúng phiên công việc. Quyền hủy phải được định nghĩa; việc một người không cần kết quả nữa không tự đồng nghĩa những người khác cũng không cần.

### Bài 4: bỏ lời gọi chờ khỏi callback

Cho quy trình minh họa:

```text
computeIfAbsent
    → gửi tác vụ vào nhóm thực thi
    → gọi get để chờ
    → trả dữ liệu
```

Hãy vẽ lại thành hai bước: công bố đối tượng đại diện công việc, rồi thực hiện hoặc chờ ở ngoài thao tác map. Sau đó thêm nhánh bộ thực thi từ chối nhận việc. Mỗi nhánh phải chỉ ra ai chịu trách nhiệm đưa đối tượng chờ đến trạng thái hoàn tất hoặc loại nó ra một cách có điều kiện.

Không chỉ xóa dòng `get` rồi coi bài toán đã xong. Kiểu giá trị của map, cách nhận kết quả và chính sách lỗi đều phải nhất quán với trạng thái đang tải.

### Các câu hỏi cần trả lời trước khi giữ một callback

1. Callback có chỉ tính kết quả cho liên kết đang xử lý không?
2. Mọi hàm mà nó gọi có tránh quay lại sửa chính map không?
3. Khối lượng công việc có giới hạn rõ và tránh chờ I/O hoặc tác vụ khác không?
4. Nếu nó trả `null` hoặc ném lỗi, lần gọi sau sẽ làm gì?
5. Có tác động bên ngoài hoặc đối tượng dùng chung nào đã bị sửa trước khi lỗi xảy ra không?
6. Khi chuyển phần dài ra ngoài, có chấp nhận tạo trùng không, hay cần dùng chung một tác vụ?
7. Nếu dùng chung tác vụ, ai bắt đầu, ai hoàn tất, ai có quyền hủy và ai được phép dọn nó?
8. Có đường phụ thuộc nào khiến một công việc chờ chính mình hoặc chờ theo một chu trình không?

Một thiết kế tốt cần giải thích được cả **giá trị được chọn** và **cách công việc tiến triển đến kết quả**. Giữ callback cục bộ, ngắn và có trách nhiệm rõ giúp hai phần đó dễ kiểm chứng trong mã và trong vận hành.
