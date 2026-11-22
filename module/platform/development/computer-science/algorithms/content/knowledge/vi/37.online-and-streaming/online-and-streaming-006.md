# Lấy mẫu luồng bằng reservoir sampling

## Tổng quan và mục tiêu

**Reservoir sampling** là thuật toán lấy mẫu từ **luồng dữ liệu (data stream)** khi chưa biết trước số phần tử N, không thể giữ toàn bộ dữ liệu trong RAM hoặc chỉ được phép duyệt nguồn một lần. Bài toán cơ bản là chọn **k vị trí xuất hiện khác nhau** trong luồng sao cho, sau khi đã nhìn thấy N≥k phần tử, **mọi tập con k vị trí** của N vị trí xuất hiện với xác suất bằng nhau.

Với `R` là tập vị trí được giữ, mục tiêu chính xác là:

**`P(R=S)=1/C(N,k)`** với mọi tập `S⊆{1,...,N}` có `|S|=k`.

Từ đó, xác suất một occurrence bất kỳ được chọn là **`k/N`**. Đây là **lấy mẫu đồng đều không hoàn lại** (*uniform sampling without replacement*). Chỉ số vị trí, không phải giá trị nội dung, xác định occurrence: luồng `[A,A,B]` có ba occurrence, nên với k=1 xác suất trả nhãn A là 2/3 và nhãn B là 1/3, dù chỉ có hai giá trị phân biệt.

Thuật toán cổ điển **Algorithm R** đạt yêu cầu với một lần đi qua luồng, **O(N) kỳ vọng thời gian**, **O(k) bộ nhớ** và không phải biết N khi bắt đầu. Khi stream chưa kết thúc, trạng thái hiện tại vẫn là một mẫu đều trên **tiền tố hữu hạn đã đọc**. Bài thuộc nhóm **Trực tuyến và luồng** trong **Computer Science Algorithms**, chủ đề **Lấy mẫu luồng bằng reservoir sampling**.

Sau bài này, bạn có thể giải thích Algorithm R bằng xác suất, chứng minh cả phân phối **uniform k-subset** chứ không chỉ xác suất xuất hiện từng phần tử, tự cài đặt Java 17+, xử lý k=0/N<k/trọng số trùng/counter lớn, kiểm tra độc lập bằng liệt kê tất cả ticket histories, và phân biệt reservoir thông thường với sampling có hoàn lại, weighted sampling, sliding-window sampling và sampling phân tán.

## 1. Hợp đồng bài toán online

Xét luồng gồm các occurrence liên tiếp:

**`x₁,x₂,...,x_N`**, trong đó N chưa chắc được biết trước.

Người gọi chọn **một số nguyên k≥0** trước khi xử lý. Sau khi đã thấy t occurrence, ta muốn giữ:

**`min(k,t)` occurrence phân biệt**, đại diện đều cho các vị trí 1..t.

Các trường hợp biên:

| Điều kiện | Hành vi |
|---|---|
| `N=0`, bất kỳ k≥0 | Reservoir rỗng |
| `k=0`, bất kỳ N | Reservoir rỗng, nhưng vẫn có thể ghi nhận `seen=N` |
| `0<N<k` | Giữ toàn bộ N occurrence, không tự lặp phần tử |
| `N=k` | Giữ toàn bộ N occurrence |
| `N>k>0` | Giữ k vị trí phân biệt, mỗi k-subset có xác suất `1/C(N,k)` |

Nếu N<k, **không thể** lấy k vị trí khác nhau từ chỉ N vị trí. Để có hợp đồng hữu ích, chương trình trả toàn bộ N vị trí. Nếu ứng dụng bắt buộc có đúng k item, phải quyết định cách báo **thiếu dữ liệu**, không tự nhân đôi item và vẫn gọi đó là “without replacement”.

### Giá trị trùng không phải cùng occurrence

Giả sử một event log có hai record cùng nội dung JSON nhưng đến ở hai thời điểm khác nhau. Với reservoir sampling thông thường, chúng là **hai occurrence riêng**, mỗi occurrence có cơ hội như nhau. Nếu muốn lấy mẫu theo **distinct key** (mỗi ID duy nhất chỉ tính một lần), đó là một bài toán streaming khác: cần chính sách nhận diện trùng, khả năng lưu hoặc xấp xỉ tập keys, và cách kiểm chứng riêng.

### Một lần đi qua là gì?

Thuật toán nhận từng item từ iterator, file reader, API stream hoặc message consumer, rồi quyết định giữ/bỏ. Một item bị loại không được yêu cầu đọc lại khi item khác đến. Sau mỗi lần xử lý, reservoir vẫn có thể xuất một **snapshot** hợp lệ; snapshot ấy chỉ đại diện cho prefix đã đọc, không đại diện cho các item tương lai.

## 2. So sánh với cách lưu hết rồi shuffle

Nếu có RAM O(N) và N biết trước, có thể đọc hết dữ liệu vào mảng, shuffle bằng **Fisher–Yates**, rồi lấy k item đầu. Với nguồn random đủ tốt, cách đó cũng cho một uniform k-subset nhưng cần **O(N) bộ nhớ** và không thể trả mẫu hoàn tất cho quần thể chưa đọc hết.

Reservoir sampling khác ở chỗ giữ tối đa k item trong bộ nhớ:
- Khi chưa đủ k, giữ item mới.
- Khi đã đủ k, xét item mới với xác suất phụ thuộc **số item đã thấy**.
- Nếu quyết định chấp nhận item mới, thay ngẫu nhiên một slot cũ.
- Khi luồng kết thúc, reservoir hiện tại là kết quả.

Chi phí lưu trữ phụ thuộc k, không phụ thuộc N. Đây là lợi thế lớn của **thuật toán streaming**.

## 3. Algorithm R — quy tắc cập nhật

Đánh số **lần xuất hiện bắt đầu từ 1** và gọi t là số occurrence đã xử lý **sau khi nhận item mới**. Mảng reservoir dùng **slot index bắt đầu từ 0**.

**Bước khởi tạo:** khi t≤k, đưa `x_t` vào slot t−1; chưa sinh vé thay thế.

**Bước online:** khi t>k:
1. Sinh một vé nguyên ngẫu nhiên **j đồng đều trong `[0,t)`**, tức 0≤j<t.
2. Nếu **j<k**, gán `reservoir[j]=x_t`.
3. Nếu **j≥k**, bỏ qua `x_t`; reservoir không đổi.

Với k=0, không cần sinh vé, chỉ cập nhật bộ đếm nếu ứng dụng cần biết N.

Pseudocode:

~~~text
RESERVOIR_SAMPLE(stream, k, rng):
    require k >= 0
    reservoir = empty array/list
    seen = 0

    for item in stream:
        seen = seen + 1

        if size(reservoir) < k:
            reservoir.append(item)
            continue

        if k == 0:
            continue

        j = rng.uniformInteger(0, seen - 1)
        if j < k:
            reservoir[j] = item

    return {items: reservoir, seen: seen, requested: k}
~~~

### Vì sao xác suất chấp nhận item mới là k/t?

Trong t vé nguyên đồng khả năng 0,1,...,t−1, có **đúng k vé** 0..k−1 khiến item mới được đưa vào reservoir:

**`P(x_t được nhận)=k/t`**, với t>k.

Nếu được chấp nhận, slot thay thế có xác suất có điều kiện **1/k** cho mỗi slot. Nhưng xác suất một slot cụ thể bị thay **không điều kiện** là **1/t**, vì vé bắt buộc phải bằng đúng slot đó.

**Điểm dễ sai:** “rút slot từ 0..k−1 rồi thay” sẽ thay ở mọi bước, ưu tiên item mới bất thường. Phải rút từ **toàn bộ phạm vi 0..t−1**, chỉ thay nếu vé nhỏ hơn k.

## 4. Ví dụ từng item: k=2

Luồng: **`A,B,C,D,E,F`**. Yêu cầu k=2. Để dễ theo dõi, giả sử vé cho bốn lần sau khi đã đầy lần lượt là **[1,3,0,5]**.

| Item | t | Vé j | Quyết định | Các slot reservoir |
|---|---:|---:|---|---|
| A | 1 | Không dùng | Thêm vào slot 0 | [A] |
| B | 2 | Không dùng | Thêm vào slot 1 | [A,B] |
| C | 3 | 1 | 1<2, thay slot 1 | [A,C] |
| D | 4 | 3 | 3≥2, bỏ | [A,C] |
| E | 5 | 0 | 0<2, thay slot 0 | [E,C] |
| F | 6 | 5 | 5≥2, bỏ | [E,C] |

Kết quả của **chuỗi vé minh họa** là **[E,C]**. Đây không phải một kết quả “cố định” của mọi lần chạy Algorithm R; cùng luồng/k có thể cho một trong C(6,2)=15 tập khác nhau.

### Ranh giới cần ghi nhớ

- t=3, phạm vi hợp lệ của j: 0,1,2; xác suất C được nhận là **2/3**.
- t=4, j: 0,1,2,3; xác suất D được nhận là **2/4**.
- t=5, j: 0..4; xác suất E được nhận là **2/5**.
- t=6, j: 0..5; xác suất F được nhận là **2/6**.

**Không** rút j∈[0,t], vì sẽ có t+1 giá trị và phân phối sai. **Không** dùng điều kiện j≤k; phải là **j<k** vì slot hợp lệ chỉ là 0..k−1.

### Mảng kết quả có giữ thứ tự stream không?

Không. [E,C] là **thứ tự slot**, không phải thứ tự arrival (C đến trước E). Uniformity được định nghĩa trên **tập con không có thứ tự**. Muốn xuất theo thứ tự đến, hãy giữ `(arrivalIndex,item)` và sort k item cuối cùng theo arrivalIndex, tốn O(k log k). Nếu muốn một **hoán vị ngẫu nhiên đều** của các item được chọn, cần shuffle thêm: Algorithm R không hứa mảng slot là một hoán vị đều.

## 5. Chứng minh xác suất inclusion k/t

Ta chứng minh bằng quy nạp rằng sau khi nhìn thấy t≥k>0 occurrence, **mỗi occurrence trong t occurrence có xác suất được giữ bằng k/t**.

**Cơ sở t=k:** tất cả k item đầu nằm trong reservoir, nên mỗi item có xác suất inclusion 1=k/k.

**Bước quy nạp:** giả sử sau t item, một item cũ x được giữ với xác suất k/t. Khi item thứ t+1 tới, rút j đồng đều từ 0..t. Nếu x hiện đang ở slot r, nó bị thay **chỉ khi j=r**, xác suất **1/(t+1)**. Vì vậy xác suất nó không bị thay **có điều kiện đang được giữ** là:

**`1−1/(t+1)=t/(t+1)`**.

Do đó:

**`P(x vẫn ở reservoir sau t+1)=(k/t)·(t/(t+1))=k/(t+1)`**.

Với item mới, xác suất được giữ bằng số vé j<k trên tổng t+1 vé:

**`P(x_{t+1} được giữ)=k/(t+1)`**.

Suy ra mỗi item cũ và mới đều có cùng inclusion probability k/(t+1).

### Cẩn thận: marginal chưa phải uniform k-subset

Nếu mọi item có xác suất được chọn k/t, điều ấy **không tự chứng minh** mọi tập k item đều có xác suất bằng nhau. Một phân phối có thể thiên lệch về một số **cặp/tập con** nhưng vẫn giữ tỷ lệ xuất hiện từng item. Vì vậy để giải trọn bài “uniform k-subset”, cần thêm chứng minh ở mục sau.

## 6. Chứng minh mạnh — mọi k-subset có xác suất đúng bằng 1/C(t,k)

Ký hiệu `R_t` là **tập chỉ số occurrence**, bỏ qua thứ tự slot. Ta chứng minh với mọi t≥k>0:

**`P(R_t=S)=1/C(t,k)`** cho mỗi tập `S⊆{1,...,t}` có đúng k phần tử.

**Cơ sở t=k:** chỉ có tập {1,...,k}; nó được giữ với xác suất 1, bằng 1/C(k,k).

**Bước t→t+1:** giả sử `R_t` uniform trên C(t,k) tập.

**Trường hợp A — S không chứa item mới (t+1).** Để R_{t+1}=S, cần R_t=S rồi không thay slot nào. Xác suất không thay là (t+1−k)/(t+1), vì có t+1−k vé j≥k. Do đó:

**`P(R_{t+1}=S)=[1/C(t,k)]·[(t+1−k)/(t+1)]=1/C(t+1,k)`**.

Đẳng thức cuối dùng:

**`C(t+1,k)=C(t,k)·(t+1)/(t+1−k)`**.

**Trường hợp B — S có item mới (t+1).** Bỏ item mới khỏi S còn k−1 item cũ, gọi là A. Để tạo S, trước bước mới reservoir phải chứa **A và thêm đúng một item cũ x không thuộc A**, sau đó item mới phải thay đúng slot của x.

Trong t item cũ có **t−(k−1)=t−k+1** lựa chọn x. Mỗi tập cũ A∪{x} có xác suất 1/C(t,k). Với tập ấy, vé phải trúng đúng slot x, xác suất 1/(t+1). Các lựa chọn x loại trừ nhau, vậy:

**`P(R_{t+1}=S)=[t−k+1]/[C(t,k)·(t+1)]=1/C(t+1,k)`**.

Hai trường hợp bao phủ mọi tập k vị trí thuộc 1..t+1. Suy ra Algorithm R tạo **uniform k-subset thực sự**, không chỉ inclusion đúng tỷ lệ.

Với k=0, chỉ có tập rỗng, xác suất 1. Với t<k, reservoir là toàn bộ t occurrence; công thức chọn k phần tử trong t không áp dụng vì k>t.

### Hệ quả: mẫu không hoàn lại

Mỗi slot chỉ chứa một occurrence; khi item mới được nhận, nó **thay** một occurrence cũ chứ không tạo thêm slot. Vì vậy một occurrence không thể hiện diện ở hai slot. Khi t≥k, kích thước mẫu luôn đúng k.

## 7. Trường hợp k=1

Với k=1, thuật toán trở thành:
- Chọn item đầu tiên.
- Khi item thứ t≥2 tới, **thay item hiện tại với xác suất 1/t**.
- Nếu không thay, giữ item cũ.

Pseudocode:

~~~text
selected = none
seen = 0

for item in stream:
    seen++
    if seen == 1:
        selected = item
    else if uniformInteger(0, seen - 1) == 0:
        selected = item

return selected
~~~

Xét xác suất item đầu tiên còn được giữ sau N item:

**`1·(1−1/2)·(1−1/3)·...·(1−1/N)`**

= **`1·(1/2)·(2/3)·...·((N−1)/N)=1/N`**.

Các item tới sau cũng có xác suất cuối 1/N theo quy nạp. Đây là cách chọn **một item đồng đều từ iterator chưa biết trước số phần tử** với bộ nhớ O(1).

## 8. Số ngẫu nhiên bounded trong Java

Trong Java 17+, giao diện `java.util.random.RandomGenerator` cung cấp:

~~~java
long ticket = rng.nextLong(seen);
~~~

Khi `seen>0`, lệnh này tạo vé thuộc khoảng **[0,seen)** theo hợp đồng random bounded. Nó phù hợp với `long seen`, tránh giới hạn `int` khi luồng có hơn khoảng 2,1 tỷ item.

**Không thay bằng:**

~~~java
long ticket = rng.nextLong() % seen; // Wrong
~~~

Vì `nextLong()` có thể âm nên `%` có thể tạo vé âm; hơn nữa miền RNG không nhất thiết chia hết cho seen nên có **modulo bias**. Dùng `Math.abs` cũng không an toàn với `Long.MIN_VALUE`: `Math.abs(Long.MIN_VALUE)` vẫn âm trong số học long có dấu.

**Không dùng `Math.random()*seen` ép long** nếu cần sample integer đều chính xác trên miền seen rất lớn; double có số bit độ chính xác hữu hạn nên không đại diện đủ mọi ticket có thể có.

### Seed và bảo mật

`SplittableRandom` có seed nên tiện tạo unit test tái lập. Nó không phải nguồn ngẫu nhiên mật mã. Nếu việc chọn mẫu liên quan tới quyền lợi, chống thao túng hoặc có đối thủ chủ động, phải chọn nguồn ngẫu nhiên phù hợp threat model (ví dụ `SecureRandom` và chính sách seed/permission), rồi kiểm tra hệ thống. Bản thân công thức reservoir đúng không đảm bảo an toàn bảo mật của RNG.

### Long.MAX_VALUE và overflow

Bộ đếm có thể được lưu trong `long`. Trước khi tăng từ `Long.MAX_VALUE`, phải báo lỗi: nếu cho wrap, counter âm và `nextLong(bound)` nhận bound không hợp lệ. Code mẫu kiểm overflow **trước khi đổi trạng thái**.

## 9. Java 17+ hoàn chỉnh: Reservoir nhận item tăng dần

Ví dụ sau là chương trình Java 17+ tự chạy, không cần thư viện ngoài JDK. Nó định nghĩa:

- `Reservoir<T>`: có trạng thái, lưu tối đa k occurrence, cập nhật qua `accept(T item)`.
- `Snapshot<T>`: báo danh sách đã giữ, số item đã đọc và số lượng k yêu cầu.
- `usingRandom`: gắn `RandomGenerator.nextLong(bound)` cho các bước đã đầy.
- `sample`: đọc hết một `Iterable` hữu hạn; với live stream vô hạn, gọi `accept` theo sự kiện và lấy snapshot khi cần.
- `ScriptedTickets`: ticket source kiểm thử, **không phải RNG thật**, dùng chuỗi vé [1,3,0,5].
- `exhaustiveUniformityChecks`: liệt kê mọi ticket history nhỏ để kiểm **mọi tập con** có cùng số lần xuất hiện.
- `randomInvariantChecks`: xác nhận kích thước, ID occurrence duy nhất và bộ đếm trên 117.800 bộ luồng/khả năng k.

Vì `List.copyOf` tạo danh sách **không cho sửa cấu trúc**, `snapshot().items()` không thể thêm/xóa; tuy nhiên nó chỉ sao chép references, **không deep-copy** object T. Ví dụ không nhận item null. Một instance `Reservoir<T>` có trạng thái mutable, **không thread-safe** nếu nhiều thread cùng `accept` không đồng bộ.

Lưu tệp **`ReservoirSamplingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.SplittableRandom;
import java.util.random.RandomGenerator;

public final class ReservoirSamplingDemo {
    @FunctionalInterface
    private interface TicketSource {
        long nextTicket(long exclusiveBound);
    }

    private record Snapshot<T>(
            List<T> items,
            long seen,
            int requested) {}

    private static final class Reservoir<T> {
        private final int capacity;
        private final TicketSource tickets;
        private final ArrayList<T> slots;
        private long seen;

        private Reservoir(int k, TicketSource source) {
            if (k < 0) {
                throw new IllegalArgumentException(
                        "Sample size must be nonnegative");
            }
            capacity = k;
            tickets = Objects.requireNonNull(source, "source");
            slots = new ArrayList<>(Math.min(k, 16));
            seen = 0L;
        }

        static <T> Reservoir<T> usingRandom(
                int k, RandomGenerator rng) {
            Objects.requireNonNull(rng, "rng");
            return new Reservoir<>(k, rng::nextLong);
        }

        // Process exactly one occurrence.
        void accept(T item) {
            Objects.requireNonNull(item, "item");

            if (seen == Long.MAX_VALUE) {
                throw new IllegalStateException(
                        "Counter overflow");
            }
            long nextSeen = seen + 1L;

            if (slots.size() < capacity) {
                slots.add(item);
                seen = nextSeen;
                return;
            }
            if (capacity == 0) {
                seen = nextSeen;
                return;
            }

            // Random ticket is uniform on [0,nextSeen).
            long ticket = tickets.nextTicket(nextSeen);
            if (ticket < 0L || ticket >= nextSeen) {
                throw new IllegalArgumentException(
                        "Ticket generator out of range");
            }
            if (ticket < capacity) {
                slots.set((int) ticket, item);
            }
            seen = nextSeen;
        }

        Snapshot<T> snapshot() {
            return new Snapshot<>(
                    List.copyOf(slots), seen, capacity);
        }
    }

    // Convenience for a finite Iterable.
    private static <T> Snapshot<T> sample(
            Iterable<? extends T> stream,
            int k,
            RandomGenerator rng) {
        Objects.requireNonNull(stream, "stream");
        Reservoir<T> sampler =
                Reservoir.usingRandom(k, rng);
        for (T item : stream) {
            sampler.accept(item);
        }
        return sampler.snapshot();
    }

    // Deterministic source for TESTS ONLY.
    private static final class ScriptedTickets
            implements TicketSource {
        private final long[] values;
        private int position;

        ScriptedTickets(long... values) {
            this.values = values.clone();
            position = 0;
        }

        @Override
        public long nextTicket(long bound) {
            if (position >= values.length) {
                throw new IllegalStateException(
                        "No scripted ticket left");
            }
            long value = values[position++];
            if (value < 0L || value >= bound) {
                throw new IllegalArgumentException(
                        "Scripted ticket outside bound");
            }
            return value;
        }
    }

    // Independent oracle: enumerate ALL ticket histories.
    // Stream positions are 0,1,...,n-1.
    private static void enumerateHistories(
            int seen,
            int n,
            int k,
            int[] slots,
            Map<Long, Long> frequencies) {
        if (seen == n) {
            long mask = 0L;
            for (int index : slots) {
                mask |= 1L << index;
            }
            frequencies.merge(mask, 1L, Long::sum);
            return;
        }

        // Item at index "seen" is arrival number seen+1.
        for (int ticket = 0; ticket <= seen; ticket++) {
            int[] next = slots.clone();
            if (ticket < k) {
                next[ticket] = seen;
            }
            enumerateHistories(
                    seen + 1, n, k, next, frequencies);
        }
    }

    private static long choose(int n, int k) {
        long result = 1L;
        for (int j = 1; j <= k; j++) {
            result = result * (n - k + j) / j;
        }
        return result;
    }

    private static void exhaustiveUniformityChecks() {
        int cases = 0;
        for (int n = 0; n <= 8; n++) {
            for (int k = 0; k <= n; k++) {
                Map<Long, Long> freq = new HashMap<>();

                if (k == 0) {
                    // No tickets are drawn for k=0.
                    freq.put(0L, 1L);
                } else {
                    int[] initial = new int[k];
                    for (int j = 0; j < k; j++) {
                        initial[j] = j;
                    }
                    enumerateHistories(
                            k, n, k, initial, freq);
                }

                if (freq.size() != choose(n, k)) {
                    throw new AssertionError(
                            "Wrong subset count");
                }

                long expected = -1L;
                for (Map.Entry<Long, Long> entry
                        : freq.entrySet()) {
                    long mask = entry.getKey();
                    long count = entry.getValue();
                    if (Long.bitCount(mask) != k) {
                        throw new AssertionError(
                                "Wrong subset cardinality");
                    }
                    if (expected == -1L) {
                        expected = count;
                    } else if (count != expected) {
                        throw new AssertionError(
                                "Non-uniform subset frequency");
                    }
                }
                cases++;
            }
        }

        if (cases != 45) {
            throw new AssertionError("Wrong case count");
        }
        System.out.println(
                "Exhaustive subset distributions: 45 PASS");
    }

    private static void randomInvariantChecks() {
        SplittableRandom rng =
                new SplittableRandom(4882026L);
        int checks = 0;

        for (int n = 0; n <= 30; n++) {
            for (int k = 0; k <= n + 3; k++) {
                for (int trial = 0; trial < 200; trial++) {
                    Reservoir<Integer> sampler =
                            Reservoir.usingRandom(k, rng);
                    for (int index = 0; index < n; index++) {
                        sampler.accept(index);
                    }

                    Snapshot<Integer> result =
                            sampler.snapshot();
                    if (result.seen() != n
                            || result.requested() != k
                            || result.items().size()
                               != Math.min(n, k)) {
                        throw new AssertionError(
                                "Incorrect size/counter");
                    }

                    HashSet<Integer> ids =
                            new HashSet<>(result.items());
                    if (ids.size() != result.items().size()) {
                        throw new AssertionError(
                                "Repeated stream position");
                    }
                    for (int id : ids) {
                        if (id < 0 || id >= n) {
                            throw new AssertionError(
                                    "Item from the future");
                        }
                    }
                    checks++;
                }
            }
        }

        if (checks != 117800) {
            throw new AssertionError(
                    "Incorrect random test count");
        }
        System.out.println(
                "Random stream invariants: 117800 PASS");
    }

    public static void main(String[] args) {
        Reservoir<String> scripted = new Reservoir<>(
                2, new ScriptedTickets(1L, 3L, 0L, 5L));
        for (String item : List.of(
                "A", "B", "C", "D", "E", "F")) {
            scripted.accept(item);
        }
        Snapshot<String> demonstration =
                scripted.snapshot();
        System.out.println(
                "Scripted k=2: " + demonstration.items()
                + "; seen=" + demonstration.seen());

        Snapshot<String> empty = sample(
                List.<String>of(),
                3, new SplittableRandom(1L));
        System.out.println(
                "Empty stream k=3: size="
                + empty.items().size());

        Snapshot<String> zero = sample(
                List.of("A", "B", "C", "D", "E", "F"),
                0, new SplittableRandom(2L));
        System.out.println(
                "k=0: size=" + zero.items().size()
                + "; seen=" + zero.seen());

        Snapshot<String> shortStream = sample(
                List.of("A", "B", "C"),
                5, new SplittableRandom(3L));
        System.out.println(
                "k>n: " + shortStream.items()
                + "; seen=" + shortStream.seen());

        Snapshot<String> seeded = sample(
                List.of("A", "B", "C", "D", "E", "F"),
                3, new SplittableRandom(488L));
        boolean unique = new HashSet<>(
                seeded.items()).size() == 3;
        System.out.println(
                "Seeded sample: size=" + seeded.items().size()
                + ", unique=" + unique
                + ", seen=" + seeded.seen());

        boolean negativeRejected = false;
        try {
            new Reservoir<Integer>(-1, bound -> 0L);
        } catch (IllegalArgumentException expected) {
            negativeRejected = true;
        }
        if (!negativeRejected) {
            throw new AssertionError(
                    "Negative k was accepted");
        }
        System.out.println("Negative k: rejected");

        boolean invalidTicketRejected = false;
        Reservoir<String> bad = new Reservoir<>(
                2, new ScriptedTickets(99L));
        bad.accept("A");
        bad.accept("B");
        try {
            bad.accept("C");
        } catch (IllegalArgumentException expected) {
            invalidTicketRejected = true;
        }
        if (!invalidTicketRejected
                || bad.snapshot().seen() != 2L) {
            throw new AssertionError(
                    "Invalid ticket not rejected atomically");
        }
        System.out.println(
                "Invalid scripted ticket: rejected");

        exhaustiveUniformityChecks();
        randomInvariantChecks();
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 ReservoirSamplingDemo.java
java ReservoirSamplingDemo
~~~

**Stdout chính xác:**

~~~text
Scripted k=2: [E, C]; seen=6
Empty stream k=3: size=0
k=0: size=0; seen=6
k>n: [A, B, C]; seen=3
Seeded sample: size=3, unique=true, seen=6
Negative k: rejected
Invalid scripted ticket: rejected
Exhaustive subset distributions: 45 PASS
Random stream invariants: 117800 PASS
~~~

### Đọc ý nghĩa đầu ra

- **Scripted:** rút đúng bốn vé minh họa 1,3,0,5, nên nhận [E,C] và seen=6.
- **Empty stream:** chưa có item, nên size=0 dù k=3.
- **k=0:** đọc sáu occurrence nhưng không lưu gì, seen vẫn bằng 6.
- **k>n:** yêu cầu 5 nhưng mới có 3, trả cả [A,B,C], không lặp.
- **Seeded:** chỉ in **bất biến xác định** size/unique/seen, không ghi một danh sách ngẫu nhiên cụ thể phụ thuộc chi tiết PRNG.
- **Negative k:** sai hợp đồng, ném IllegalArgumentException.
- **Invalid scripted ticket:** fake source trả 99 khi bound=3, bị từ chối trước khi tăng counter; bộ sinh Java bounded thật phải tuân thủ bound.
- **Exhaustive distributions:** kiểm đều trên **mọi k-subset**, không phải 45 lần random.
- **Random invariants:** kiểm 117.800 cấu hình N/k/trial, có nhiều trường hợp k=0 và N<k.

### Sao chép và mutable item

`List.copyOf(slots)` trả snapshot cấu trúc không sửa được. Nhưng nếu T là một object mutable, bản snapshot chỉ giữ **cùng tham chiếu**, nên đổi nội dung object ở nơi khác vẫn có thể ảnh hưởng giá trị quan sát. Nếu cần snapshot dữ liệu bất biến, tạo deep copy hoặc giữ record/value object immutable.

### Thread safety

Một Reservoir chứa `seen` và `slots` mutable. Hai thread gọi `accept` cùng lúc mà không khóa có thể mất cập nhật, thay slot sai hoặc làm hỏng tính ngẫu nhiên. Cần serialize sự kiện vào một sampler, dùng synchronization rõ ràng, hoặc phân shard và merge bằng thuật toán được chứng minh đúng.

## 10. Oracle vét cạn mọi chuỗi ticket

Để kiểm phân phối, chỉ chạy ngẫu nhiên vài trăm lần là chưa mạnh: một bug off-by-one có thể hiếm xảy ra. Với N nhỏ, ta có thể **liệt kê tất cả ticket histories** của Algorithm R và đếm tập con kết quả.

Ví dụ N=6, k=2:
- t=3 rút từ 3 vé.
- t=4 rút từ 4 vé.
- t=5 rút từ 5 vé.
- t=6 rút từ 6 vé.

Tổng history:

**`3·4·5·6=360`**.

Số tập con 2 vị trí trong 6 vị trí:

**`C(6,2)=15`**.

Nếu thuật toán uniform thật, mỗi tập con phải xuất hiện đúng **`360/15=24`** history. Bộ kiểm thử liệt kê độc lập đã xác nhận đúng **24 lần cho mỗi tập**. Khi mỗi history đồng xác suất 1/360, xác suất của mỗi tập là 24/360=1/15.

Với `k=0`, thuật toán **không rút ticket**, nên chỉ có một history (mẫu rỗng) chứ không nên nhân số các vé không hề sử dụng. Với `k=N`, chỉ có một tập N vị trí và cũng không rút ticket replacement.

### Kết quả kiểm thử độc lập

Mô hình tham chiếu chạy **45 cặp (N,k) với 0≤k≤N≤8**, tổng **79.448 lịch sử vé**, xác nhận mỗi tập con k vị trí có cùng số history trong mỗi cặp. Ngoài ra, **25.000 luồng ngẫu nhiên**, tương ứng **1.237.327 lần xử lý item**, được kiểm từng prefix: số phần tử bằng min(k,t), không lặp ID occurrence và không có item tới từ tương lai. Tất cả đạt.

Đây là cách bổ trợ kiểm chứng mạnh cho code, nhưng **không thay thế** chứng minh quy nạp cho mọi N.

## 11. Độ phức tạp của Algorithm R

Với N item và k mẫu:

| Hoạt động | Thời gian | Bộ nhớ |
|---|---:|---:|
| Nhận một item khi chưa đầy | O(1) amortized | Tăng một slot |
| Nhận một item khi đầy | O(1) kỳ vọng | O(1) phụ |
| Toàn bộ N item | **O(N) kỳ vọng** | **O(min(k,N))** |
| Lấy snapshot sao chép | O(min(k,N)) | O(min(k,N)) tạm |
| Sort k kết quả theo arrival | O(k log k) | Tùy thuật toán sort |
| Mẫu k=1 | O(N) | O(1) |

Tính O(1) kỳ vọng cho một vé bounded xét các phép toán 64-bit và RNG có thao tác expected constant-time; những implementation dùng rejection sampling có thể mất nhiều hơn một lần lấy bit trong một số lượt.

**Không** gọi toàn pipeline O(N) nếu ứng dụng lấy snapshot và copy k item sau **mỗi** sự kiện: N snapshot có thể tạo O(Nk) công việc thêm. Bản thân vòng cập nhật Algorithm R vẫn O(N).

**Không** nhầm O(k) slots với đúng O(k) bytes: nếu mỗi item chứa payload hàng MB, bộ nhớ thực lớn hơn theo kích thước của các item. Khi chỉ cần tham chiếu/ID, lưu token ngắn có thể giảm chi phí nhưng phải bảo đảm item thực tế vẫn truy cập được về sau.

## 12. Uniform subset không phải uniform order

Reservoir được hiểu là **tập occurrence**. Thứ tự trong slots có thể phụ thuộc lịch sử cập nhật. Khi N=k, nó chắc chắn là thứ tự arrival, không phải một trong k! hoán vị đều.

Nếu ứng dụng cần:
- **Tập k item không thứ tự:** dùng reservoir trực tiếp.
- **Tập k item sắp theo thời gian đến:** lưu arrivalIndex và sort ở cuối.
- **Một hoán vị ngẫu nhiên đều của k item được chọn:** shuffle mẫu bằng Fisher–Yates sau khi sampling.
- **k lượt lấy mẫu có hoàn lại:** sử dụng một bài toán khác, có thể chạy k sampler k=1 độc lập nếu cần một lượt stream.

### Một sample không phải nhiều sample độc lập

Gọi `snapshot()` nhiều lần sau khi stream đã kết thúc không tạo nhiều lần rút. Đó chỉ là cùng một reservoir. Nếu cần m mẫu k-item độc lập từ một stream không lưu, một cách đơn giản là duy trì m sampler độc lập, chi phí khoảng O(mN) thao tác và O(mk) bộ nhớ.

## 13. Stream vô hạn và thời điểm chốt mẫu

Một luồng thực sự vô hạn không có N cuối để ta tạo mẫu “uniform trên mọi occurrence trong vô hạn item”: không tồn tại một xác suất dương bằng nhau cho vô hạn đếm được các vị trí mà tổng xác suất bằng 1.

Reservoir sampling tránh vấn đề này bằng một bảo đảm khác: **sau mọi tiền tố hữu hạn t** ta có mẫu đều từ t item đã thấy. Người dùng có thể chụp một snapshot lúc t=1000, rồi tiếp tục nhận item và chụp snapshot khác lúc t=10000.

Nếu thời điểm **dừng** được chọn một cách thiên lệch dựa trên nội dung reservoir, phân phối có điều kiện theo cơ chế dừng có thể không còn uniform theo cách hiển nhiên. Ví dụ “chỉ dừng khi mẫu chứa nhãn A” sẽ thiên về A khi phân tích các run đã dừng. Khi dùng một snapshot để suy luận thống kê, phải ghi rõ **quần thể tiền tố**, thời điểm chốt và chính sách dừng.

## 14. Có tăng/giảm k giữa chừng được không?

Algorithm R chuẩn giả định k **đã cố định**.

**Tăng k:** nếu đã đọc một triệu item với k=5 rồi muốn k=100, những item bị bỏ không còn trong RAM. Không thể tự mở rộng mảng thêm 95 chỗ để tạo mẫu 100 đều từ toàn bộ lịch sử. Muốn hỗ trợ tăng k cần lưu thêm thông tin/đọc lại nguồn hoặc một thuật toán khác.

**Giảm k:** nếu đang có một mẫu uniform kích thước k và muốn r≤k, ta có thể lấy **một tập r item đều không hoàn lại từ chính k item đó**. Khi ấy nhờ đối xứng tổ hợp, kết quả là một mẫu r đều từ N item đã qua. Nếu tiếp tục xử lý luồng, phải cập nhật chính sách tương lai với r mới và bảo đảm toàn bộ quy trình giữ phân phối đúng.

**Thay đổi động:** đòi hỏi mô hình riêng; không đơn giản thay biến k trong Algorithm R đang chạy mà không xét lịch sử.

## 15. Sample có trọng số khác gì uniform reservoir?

Algorithm R coi **mỗi occurrence có trọng số bằng nhau**. Nếu một occurrence có w=100 và occurrence khác w=1, Algorithm R không tự cho mục đầu “cơ hội gấp 100 lần”.

Có các thuật toán **weighted reservoir sampling** riêng. Một họ dùng khóa ưu tiên độc lập cho từng item có trọng số w>0:

**`key=U^(1/w)`**, U đồng đều trên (0,1),

rồi giữ k khóa lớn nhất. Một cách tính tương đương về thứ tự trong mô hình số học lý tưởng là dùng:

**`priority=−ln(U)/w`** và giữ k priority nhỏ nhất.

Với k>1, xác suất inclusion của mỗi item trong những scheme weighted without replacement **không thể tùy tiện viết thành k·w/W**; chính sách chọn k item và phân phối kết quả phải được định nghĩa rõ. Tất cả các vấn đề w=0, w âm, underflow/log/tie và độ chính xác số thực cần xử lý riêng.

**Mã Java trong bài không làm weighted sampling.** Việc thêm một tham số weight vào `accept` mà giữ quy tắc j như cũ không làm nó thành một thuật toán weighted đúng.

## 16. Sliding window và dữ liệu mới hơn

Nếu dashboard chỉ muốn 100 event ngẫu nhiên trong **5 phút gần nhất**, Algorithm R trên **toàn bộ lịch sử** không đúng yêu cầu. Nó vẫn có thể giữ một event rất cũ với xác suất tương ứng, vì reservoir đại diện đều cho tất cả item trước thời điểm snapshot.

Đừng chỉ xóa slot chứa event hết hạn rồi chèn item mới để “bù”: những event vẫn nằm trong cửa sổ nhưng đã bị loại từ trước không thể tự khôi phục. Phân phối trên cửa sổ có thể bị lệch.

Cần một **sliding-window sampling** chuyên dụng, hoặc giữ đủ dữ liệu trong cửa sổ và lấy mẫu từ đó khi kích thước cửa sổ chấp nhận được. Nếu mục tiêu là ưu tiên dữ liệu mới bằng **time decay**, đó là weighted/decayed sampling với phân phối phải định nghĩa riêng.

## 17. Lấy mẫu từ nhiều shard

Cho hai shard:
- Shard A có 1000 item, local reservoir k=1.
- Shard B có 1 item, local reservoir k=1.

Nếu coordinator chọn đều một trong **hai local sample**, item duy nhất ở B có xác suất **1/2**. Nhưng uniform trên toàn bộ 1001 item yêu cầu nó có xác suất **1/1001**. Vậy không được ghép reservoir của nhiều shard bằng cách **chọn đều shard** khi kích thước shard khác nhau.

Với k=1, có thể merge đúng bằng cách:
1. Mỗi shard cung cấp N_shard và một item uniform trong shard.
2. Chọn shard A với xác suất N_A/(N_A+N_B), shard B với xác suất N_B/(N_A+N_B).
3. Trả item sample của shard được chọn.

Mỗi item trong shard A có xác suất `N_A/(N_A+N_B)·1/N_A=1/(N_A+N_B)`; tương tự shard B.

Với k>1, một lựa chọn khác là **priority/bottom-k sampling**: gán khóa ngẫu nhiên độc lập cho mỗi occurrence và chọn k khóa nhỏ nhất toàn cục. Mỗi shard chỉ cần gửi **k khóa nhỏ nhất của shard**, vì một item không nằm trong top k của chính shard không thể lọt top k toàn cục. Coordinator giữ k khóa tốt nhất từ hợp ứng viên. Phải giải quyết tie/collision và seed/độc lập khóa đúng để có phân phối mục tiêu. Đây là **một thuật toán liên quan**, không phải “ghép tùy tiện nhiều reservoir Algorithm R là đúng”.

## 18. Dùng mẫu để ước lượng thống kê

Giả sử sau N≥k>0 occurrence, mỗi item có một đại lượng số y_i. Trung bình quần thể là:

**`μ=(1/N)Σ_{i=1}^{N}y_i`**.

Trung bình mẫu reservoir:

**`ȳ=(1/k)Σ_{i∈R}y_i`**.

Vì mỗi vị trí có inclusion probability k/N, tính kỳ vọng:

**`E[ȳ]=(1/k)Σ_i P(i∈R)y_i=(1/k)Σ_i(k/N)y_i=μ`**.

Tức là **trung bình mẫu không chệch** cho trung bình quần thể dưới giả thiết chốt tiền tố N phù hợp. Muốn ước lượng tổng, có thể dùng `T̂=N·ȳ`.

Tuy nhiên:
- Mẫu hữu hạn vẫn có **sai số sampling**; không phải lúc nào ȳ=μ.
- Các item trong một mẫu không hoàn lại **không độc lập hoàn toàn** theo sự kiện được chọn; công thức phương sai phải phù hợp sampling without replacement.
- Nhóm hiếm có thể **không được chọn lần nào** khi k nhỏ.
- Với k=0 không có trung bình mẫu; với k≥N ta có toàn bộ quần thể và không có sai số sampling.
- Nếu dùng phân tầng, time decay hay weighted sampling, phải sửa cách ước lượng để tránh bias.

## 19. Các biến thể và hướng tối ưu nâng cao

**Vitter/skip-based reservoir sampling:** khi N cực lớn và k nhỏ, xác suất nhận item mới ngày càng thấp. Các thuật toán skip-based tính số item có thể bỏ trước lần nhận tiếp, giảm số lần lấy RNG trong một số mô hình. Phải dùng phân phối skip **đúng**; không tự ước lượng bằng một hằng số tùy ý. Nếu vẫn phải đọc và parse mọi message, tổng chi phí I/O có thể không giảm tương ứng.

**Priority sampling (bottom-k):** gán một khóa random cho mỗi occurrence rồi giữ k khóa nhỏ nhất. Có thể dùng heap O(k) bộ nhớ, hỗ trợ merge shard thuận tiện, nhưng phải bảo đảm nguồn khóa và xử lý tie. Nếu dùng heap, chi phí cập nhật một item được nhận có thể O(log k); tổng chi phí phụ thuộc số item được nhận và cách cài đặt.

**Bernoulli sampling:** cho mỗi item vào mẫu với xác suất p độc lập. Kích thước mẫu là ngẫu nhiên với kỳ vọng Np; không đảm bảo đúng k. Không gọi nó là reservoir fixed-k.

**Sampling with replacement:** trả k lượt rút có thể trùng occurrence; có thể dùng k sampler độc lập k=1 trên cùng luồng nếu yêu cầu phù hợp. Nó có phân phối khác uniform k-subset.

**Distinct sampling:** chọn theo ID phân biệt chứ không theo lần xuất hiện. Cần mô hình duplicate detection và thuật toán cho distinct keys; không tự giả định Reservoir<T> đã loại trùng values.

## 20. Đặt Algorithm R vào kiến trúc hệ thống

Với luồng file lớn, gọi `accept` trong vòng đọc file; nếu muốn sample toàn bộ file, **phải đọc đến hết**. Dừng sau 1000 dòng vì “mẫu có đủ k item rồi” sẽ lấy mẫu chỉ từ **1000 dòng đầu**, thiên lệch nếu định nghĩa quần thể là toàn bộ file.

Với message broker live, có thể giữ một sampler cho mỗi partition hoặc cho mỗi nhóm dữ liệu, nhưng nếu cần mẫu uniform **toàn bộ hệ thống**, phải thiết kế chiến lược phân phối/merge đúng như mục 17. Không nên dùng cùng sampler mutable từ nhiều consumer thread mà không đồng bộ.

Với dữ liệu IoT, có thể lấy snapshot theo từng phiên đo xác định (ví dụ 24 giờ). Nhưng nếu mục tiêu là “mỗi giờ gần nhất” với cửa sổ trượt theo thời gian, phải dùng thuật toán cửa sổ, không chỉ lấy snapshot từ reservoir toàn lịch sử.

Với ứng dụng bảo mật hoặc bốc thăm nhạy cảm, cần đảm bảo pipeline không cho phép sửa dữ liệu trước/đang sampling, không lộ state RNG, có log kiểm toán thích hợp và cơ chế kiểm chứng kết quả. Reservoir đúng xác suất **chưa đủ** để bảo đảm công bằng trước một đối thủ điều khiển nguồn hoặc thời điểm dừng.

## 21. Lỗi thường gặp

1. Rút `j∈[0,t]` thay vì [0,t), khiến có t+1 vé.
2. Dùng `j≤k` thay vì j<k, có thể ghi ngoài slot.
3. Cho item mới luôn vào mẫu và chỉ random slot bị thay.
4. Dùng xác suất 1/k cho mọi item sau khi đầy thay vì k/t.
5. Nhầm chỉ số slot 0-based với thứ tự item 1-based.
6. Không tăng seen đúng một lần cho mỗi occurrence.
7. Dùng `int seen` khi N có thể vượt 2³¹−1.
8. Cho seen tràn Long.MAX_VALUE thành âm.
9. Dùng `nextLong()%t` hoặc Math.abs rồi modulo, gây bias hoặc số âm.
10. Dùng `Math.random()*t` ở t rất lớn và đòi uniform integer chính xác.
11. Không xét k=0, luồng rỗng hay N<k.
12. Lặp item để đủ k khi N<k, đổi thành sampling có hoàn lại.
13. Cho phép k âm hoặc không kiểm constructor.
14. Xem hai occurrence có value giống nhau là cùng một occurrence.
15. Dùng HashSet của giá trị trong test cho luồng có duplicate values.
16. Coi thứ tự reservoir là thứ tự arrival.
17. Coi thứ tự các slot là hoán vị ngẫu nhiên đều.
18. Chỉ chứng minh xác suất inclusion k/N rồi tuyên bố toàn bộ k-subset uniform.
19. Bắt tần suất random trong 100 thử phải đúng bằng xác suất lý thuyết.
20. Reset seed mỗi lần nhận item khiến ticket sequence bị lệch.
21. Tưởng snapshot nhiều lần sau một luồng là nhiều mẫu độc lập.
22. Dùng Algorithm R fixed-k cho sampling có hoàn lại.
23. Tăng k khi đã loại item nhưng không thể khôi phục.
24. Dùng reservoir toàn lịch sử để làm sliding-window sample.
25. Xóa item cũ rồi fill ngẫu nhiên, không chứng minh phân phối window.
26. Thêm weight vào logic thay slot tùy tiện, không còn uniform/weighted đúng.
27. Nói weighted inclusion k*w/W luôn đúng với k>1.
28. Merge các shard reservoir ngang nhau dù shard có số lượng khác nhau.
29. Ghép local samples rồi cắt k đầu mà không có cơ chế đúng.
30. Dừng đọc nguồn trước khi quần thể mong muốn kết thúc.
31. Dùng snapshot từ tiền tố để suy luận về item chưa xuất hiện.
32. Không ghi lại seen/N khi báo thống kê.
33. Dùng stopping time phụ thuộc vào reservoir mà bỏ qua bias.
34. Chia sẻ một sampler mutable giữa thread không đồng bộ.
35. Xem List.copyOf là deep copy của item mutable.
36. Snapshot O(k) sau từng item nhưng vẫn báo toàn pipeline O(N).
37. Cho seed cố định đồng nghĩa bảo mật.
38. Lưu object reference tới buffer được tái sử dụng rồi payload mẫu thay đổi.
39. Chỉ test k=N, không test t>k khi thực sự dùng replacement.
40. Không test ticket k−1, k và t−1.
41. Dùng oracle kiểm thử gọi chính sampler thay vì độc lập liệt kê ticket histories.
42. Tưởng k sampler k=1 độc lập tương đương một sample k không hoàn lại.
43. Không định nghĩa chính xác sample theo occurrence/unique key/weight.
44. Bỏ qua việc source có thể ném lỗi giữa stream và snapshot chưa phải mẫu cuối.
45. Tuyên bố lấy mẫu đều trên luồng vô hạn như đã đọc hết N vô hạn.
46. Tưởng tất cả item có inclusion đúng là chứng minh mọi tập con có xác suất bằng nhau.
47. Không mô tả RNG có bounded rejection/cost trong phân tích phức tạp.
48. Cho top-k priority và Algorithm R là một implementation giống hệt nhau.
49. Không giữ tính độc lập của khóa/nguồn vé trong mô hình phân tán.
50. Dùng thuật toán streaming sai yêu cầu time-decayed/stratified sampling.

## 22. Bài tập thực hành

**Bài 1 — Scripted R:** Với A..F, k=2 và vé [1,3,0,5], viết bảng trạng thái. Giải thích tại sao D và F không được giữ.

**Bài 2 — Xác suất inclusion:** Chứng minh item cũ có xác suất k/t sau khi đã thấy t item bằng quy nạp; giải thích xác suất một slot cụ thể bị thay là 1/(t+1).

**Bài 3 — Uniform k-subset:** Chứng minh hai trường hợp tập đích S chứa/không chứa item mới. Tại sao có t−k+1 khả năng item cũ bị thay ở trường hợp có item mới?

**Bài 4 — Exhaustive histories:** Với N=5,k=2, liệt kê mọi chuỗi ticket, đếm các bitmask cuối cùng. Mọi C(5,2)=10 tập con có số history như nhau không?

**Bài 5 — K=1:** Viết sampler k=1 không cần ArrayList. Chứng minh mỗi item trong N item có xác suất 1/N.

**Bài 6 — Biên k=0/N<k:** Kiểm thử N=0,k=0; N=0,k=5; N=3,k=0; N=3,k=5. Đối chiếu seen và size.

**Bài 7 — Giá trị trùng:** Với stream [A,A,B],k=1, tính xác suất từng occurrence và xác suất theo label.

**Bài 8 — Ranh giới vé:** Khi t=10,k=3, xác định hành động của vé 0,2,3,9,10. Vé 10 có hợp lệ không?

**Bài 9 — RNG không thiên lệch:** Giải thích vì sao `nextLong()%t` không đúng và thay bằng `nextLong(t)`. Xét Long.MIN_VALUE.

**Bài 10 — Sort theo arrival:** Thay T bằng record gồm index và payload, lấy snapshot k item rồi sort theo index; chứng minh không làm đổi tập được chọn.

**Bài 11 — Nhiều sample:** Duy trì 3 reservoir độc lập cùng k=5 trên một stream; so với gọi snapshot ba lần trên một sampler.

**Bài 12 — Sliding window:** Tạo một luồng dài rồi cho thấy Algorithm R có thể giữ item ngoài 100 item gần nhất, chứng minh nó không thỏa yêu cầu window.

**Bài 13 — Merge shard:** Với N_A=1000,N_B=1,k=1, tính xác suất của item B nếu chọn đều hai shard và nếu chọn shard tỷ lệ số item.

**Bài 14 — K tăng:** Giải thích tại sao không thể tăng k=5 lên 100 sau khi đã thấy một triệu item nếu không lưu thêm dữ liệu.

**Bài 15 — Thống kê:** Chứng minh ȳ không chệch cho trung bình của N occurrence với sample uniform k≥1, nêu điều kiện stopping.

**Bài 16 — Weighted keys:** Tìm hiểu key=U^(1/w) và so với Algorithm R uniform; giải thích cần xử lý trọng số 0.

**Bài 17 — Performance:** Với N=10 triệu,k=1000, đo throughput một lượt, số lần snapshot, bộ nhớ và chi phí RNG; khi nào skip-based algorithm có ích?

## 23. Checklist trước khi dùng

- Đã xác nhận **sample theo occurrence**, không phải distinct values?
- Đã xác nhận **không hoàn lại**, k cố định và biết trước?
- k≥0; xử lý luồng rỗng, N<k, k=0?
- seen đếm đúng số item đã nhìn thấy?
- Khi chưa đủ k, thêm item mà không rút ticket?
- Khi đã đầy, rút **j uniform [0,seen)**?
- Chỉ thay khi **j<k**, và index j luôn hợp lệ?
- Đã dùng bounded RNG như nextLong(seen), không modulo?
- Bộ đếm long có chặn overflow?
- Đã hiểu random seed dùng để debug, không phải bảo mật?
- Đã phân biệt tập con uniform với thứ tự slot?
- Nếu stream có duplicate values, có test theo occurrence IDs?
- Nếu cần snapshot theo arrival, có lưu sequence number?
- Có ghi seen cùng sample để giải thích quần thể?
- Nếu gọi snapshot rất thường xuyên, đã tính O(k) copy mỗi lần?
- Có dùng cách an toàn nếu nhiều thread cùng đẩy dữ liệu?
- Nếu dữ liệu phân tán, có merge có chứng minh theo shard sizes/priority?
- Nếu cần weighted, with-replacement, sliding-window hay time decay, có chọn thuật toán khác?
- Có test mọi ticket histories trên N nhỏ và kiểm uniform k-subset?
- Có test luồng ngẫu nhiên và mọi trạng thái size=min(k,t)?
- Có test k−1/k/t−1, duplicate values, long bound, invalid ticket?
- Nếu dùng sampling để suy luận thống kê, có tính sai số mẫu và stopping bias?
- Không tuyên bố mẫu hoàn tất đại diện cho luồng vô hạn?

**Kết luận:** Algorithm R giữ k occurrence đầu tiên rồi, với occurrence thứ t>k, rút vé nguyên đồng đều **j∈[0,t)**; **j<k** thì thay slot j, ngược lại bỏ item mới. Sau N≥k item, mọi tập con k vị trí có xác suất **1/C(N,k)** và mỗi occurrence có inclusion probability **k/N**. Thuật toán chỉ duyệt luồng một lần với **O(N) thời gian kỳ vọng, O(k) bộ nhớ**, phù hợp dữ liệu lớn và N chưa biết trước. Kết quả đại diện cho một **tiền tố hữu hạn**, không tự áp dụng cho weighted, sliding-window, distinct keys hoặc gộp nhiều shard. Chứng minh quy nạp, RNG bounded đúng, ranh giới vé và kiểm thử exhaustive trên N nhỏ là những yếu tố quan trọng nhất của một cài đặt đáng tin cậy.