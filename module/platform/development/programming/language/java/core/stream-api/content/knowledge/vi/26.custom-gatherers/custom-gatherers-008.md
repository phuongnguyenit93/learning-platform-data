# Xây dựng toán tử gộp phần tử liên tiếp theo khóa

## 1. Bài toán: gom các đoạn liên tiếp, không gom toàn cục

Trong **Java Stream API**, `filter` và `map` phù hợp với xử lý từng phần tử; `groupingBy` gom những phần tử cùng khóa trên **toàn bộ** luồng. Tuy nhiên, nhiều bài toán nhật ký và chuỗi sự kiện yêu cầu gom **những phần tử liên tiếp có cùng khóa**, đồng thời **giữ ranh giới khi khóa thay đổi**.

Ví dụ một hệ thống nhận sự kiện theo trình tự:

```text
Đầu vào (theo thứ tự):
A1  A2  A3  B1  B2  A4  C1  C2
│        │  │    │  │   │    │
└── A ───┘  └ B ─┘  A4  └ C ─┘

Kết quả mong muốn:
Run(A, [A1, A2, A3])
Run(B, [B1, B2])
Run(A, [A4])
Run(C, [C1, C2])
```

Hai đoạn có khóa `A` **không được gộp làm một**, vì ở giữa có đoạn khóa `B`. Đây là phép *run-length grouping*, *group adjacent by key* hoặc *group consecutive elements by key*. Nó xuất hiện khi cần:

- Gom các trạng thái giống nhau liên tiếp trong chuỗi sự kiện.
- Gộp các bản ghi log có cùng mức độ ưu tiên trong một khoảng liên tục.
- Tạo những đợt hoạt động liên tiếp của một thiết bị.
- Đếm số lần chuyển trạng thái hoặc tóm tắt từng đoạn của luồng dữ liệu.
- Chuyển các bản ghi đã được sắp theo khóa thành từng khối để xử lý tiếp.

Bài này thuộc chương **Xây dựng Gatherer tùy biến** của module `JAVA_STREAM_API`. Chúng ta sẽ tự tạo một toán tử để dùng như sau:

```java
List<Run<String, Event>> runs = events.stream()
        .gather(groupConsecutiveBy(Event::type))
        .toList();
```

Ở đây `groupConsecutiveBy` là **hàm do chúng ta tự xây dựng**, trả về một `Gatherer`. Nó không phải phương thức dựng sẵn của `Gatherers` trong thư viện chuẩn.

**Phiên bản Java:** Stream Gatherers trở thành tính năng chính thức từ **Java 24** (JEP 485); chúng từng ở giai đoạn preview trong Java 22 và Java 23. Bài học và chương trình hoàn chỉnh dùng **JDK 24+** và không cần `--enable-preview` khi biên dịch trên JDK 24 trở lên. Trên Java 17/21, mã `Stream.gather` chưa phải API chuẩn sẵn có.

## 2. Phân biệt groupingBy và nhóm liên tiếp

Cho các phần tử có khóa:

```text
A, A, B, A, B, B
```

Hai yêu cầu có kết quả khác nhau:

| Yêu cầu | Cách hiểu | Kết quả |
| --- | --- | --- |
| Phân nhóm toàn cục | Mọi phần tử cùng khóa thuộc cùng nhóm | `A → [A,A,A]`; `B → [B,B,B]` |
| Phân nhóm liên tiếp | Khóa đổi thì kết thúc nhóm hiện tại | `[A,A]`, `[B]`, `[A]`, `[B,B]` |

`Collectors.groupingBy(classifier)` là terminal collector trả về `Map<K, List<T>>`. Nó không giữ được **số lần một khóa xuất hiện ở các đoạn tách rời** nếu chỉ lưu một entry cho mỗi khóa.

Ngược lại, toán tử nhóm liên tiếp tạo một **Stream các nhóm**. Điều này cho phép nối tiếp các thao tác:

```java
events.stream()
        .gather(groupConsecutiveBy(Event::type))
        .filter(run -> run.items().size() >= 2)
        .map(run -> run.key() + "=" + run.items().size())
        .forEachOrdered(System.out::println);
```

Kết quả của `gather` vẫn là Stream và có thể dùng tiếp `map`, `filter`, `limit` hoặc `collect`. Mỗi nhóm được phát ra khi biết rằng nó đã kết thúc, hoặc khi nguồn đã hết.

### Tại sao distinct hay windowFixed không thay thế được?

`distinct` loại phần tử trùng theo `equals` nhưng không gom phần tử thành đoạn. `Gatherers.windowFixed(n)` tạo cửa sổ cố định theo số lượng `n`, không căn cứ vào chỗ **khóa đổi**. `groupingBy` lại gộp trên toàn bộ nguồn. Vì thế, nhóm liên tiếp là một ví dụ thực tế cho **Gatherer có trạng thái** (*stateful Gatherer*).

## 3. Kiến trúc Gatherer trong Java 24

`java.util.stream.Gatherer<T, A, R>` là giao thức cho thao tác trung gian có thể tích lũy trạng thái, phát ra không, một hoặc nhiều phần tử đầu ra cho các phần tử đầu vào. Ý nghĩa ba tham số kiểu:

| Tham số kiểu | Ý nghĩa trong bài |
| --- | --- |
| `T` | Một phần tử đầu vào, ví dụ `Event`. |
| `A` | Trạng thái tích lũy nội bộ, ví dụ khóa hiện tại và danh sách bản ghi của đoạn. |
| `R` | Một phần tử đầu ra, ví dụ `Run<String, Event>`. |

Các thành phần của một Gatherer:

1. **Initializer:** tạo trạng thái `A` mới cho lượt đánh giá.
2. **Integrator:** nhận `(state, element, downstream)`, cập nhật trạng thái và có thể phát phần tử mới bằng `downstream.push(...)`.
3. **Combiner:** định nghĩa cách ghép trạng thái của các phần chia song song, nếu muốn Gatherer hỗ trợ xử lý song song tại bước này.
4. **Finisher:** được gọi khi không còn đầu vào để tiêu thụ, có thể phát kết quả cuối còn giữ trong trạng thái.

Đối với bài toán nhóm liên tiếp, ranh giới phụ thuộc **thứ tự phần tử**, nên ta chủ động dùng **Gatherer tuần tự**:

```java
Gatherer.ofSequential(
        initializer,
        integrator,
        finisher
)
```

Chữ ký được sử dụng về mặt ý tưởng là:

```java
static <T, A, R> Gatherer<T, A, R> ofSequential(
        Supplier<A> initializer,
        Gatherer.Integrator<A, T, R> integrator,
        BiConsumer<A, Gatherer.Downstream<? super R>> finisher
)
```

Một Gatherer tạo bằng `ofSequential` không cung cấp combiner có khả năng ghép trạng thái ở ranh giới tùy ý. Đây là **lựa chọn đúng trước tiên**: việc chia luồng thành nhiều phần song song có thể cắt đôi một nhóm, và một phép kết hợp ngây thơ sẽ cho kết quả sai.

### Downstream.push và tín hiệu dừng

Trong integrator, `downstream.push(output)` chuyển một nhóm hoàn chỉnh sang công đoạn sau. Giá trị `boolean` trả về cho biết downstream **còn chấp nhận thêm đầu ra hay không**. Khi nó trả `false`, integrator phải **ngừng yêu cầu xử lý đầu vào tiếp** bằng cách trả `false`.

Tín hiệu này quan trọng nếu pipeline phía sau dùng `limit(n)` hoặc một terminal operation dừng sớm. Không nên bỏ qua giá trị trả về của `push` rồi vẫn tiếp tục xử lý nguồn không cần thiết.

## 4. Trạng thái tối thiểu cần lưu

Một toán tử nhóm liên tiếp cần biết:

- **Đã mở nhóm chưa?** `active`, để phân biệt trạng thái chưa có phần tử với trường hợp khóa hiện tại thật sự bằng `null`.
- **Khóa hiện tại:** `key`, dùng so sánh với khóa của phần tử mới.
- **Các phần tử của nhóm hiện tại:** `items`, danh sách đang được tích lũy.

```text
Trước khi nhận đầu vào:
active=false, key=(chưa có), items=[]

Nhận A1:
active=true, key=A, items=[A1]

Nhận A2:
key vẫn A, items=[A1,A2]

Nhận B1:
phát Run(A,[A1,A2])
chuyển sang key=B, items=[B1]

Hết nguồn:
phát Run(B,[B1])
```

**Invariant** cần giữ: khi `active=true`, `items` chứa **đúng các phần tử của đoạn đang mở**, theo encounter order, và tất cả có khóa bằng `key` theo quy tắc so sánh đã chọn.

Không dùng `key == null` để nói "chưa có nhóm", vì classifier có thể hợp lệ trả `null`. Thay vào đó, `active` mô tả trạng thái riêng.

### Tại sao phải chụp bản sao trước khi phát?

Nếu phát thẳng `items` rồi gọi `items.clear()` để bắt đầu nhóm mới, **nhóm vừa phát cũng có thể thành rỗng**, vì downstream vẫn giữ tham chiếu tới cùng List.

Sai:

```java
downstream.push(new Run<>(state.key, state.items));
state.items.clear(); // Có thể xóa luôn dữ liệu của Run đã phát.
```

Đúng: tạo **snapshot** của nhóm trước khi phát:

```java
List<T> snapshot = Collections.unmodifiableList(
        new ArrayList<>(state.items)
);
downstream.push(new Run<>(state.key, snapshot));
```

`Collections.unmodifiableList` ngăn sửa **cấu trúc danh sách** qua kết quả, còn `new ArrayList<>(...)` cắt đứt chia sẻ với bộ đệm đang tái sử dụng. Đây vẫn chỉ là **bản sao nông**: đối tượng phần tử mutable cần được xử lý riêng nếu yêu cầu bất biến sâu.

## 5. Thuật toán integrator: ba trường hợp

Với phần tử mới `element`, ta tính:

```java
K nextKey = classifier.apply(element);
```

Sau đó xét ba trường hợp:

| Trạng thái | Hành động | Có phát nhóm ngay không? |
| --- | --- | --- |
| Chưa có nhóm (`!active`) | Mở nhóm mới với `nextKey` và `element` | Không |
| `Objects.equals(key, nextKey)` | Thêm phần tử vào nhóm đang mở | Không |
| Khóa khác | Phát snapshot nhóm cũ, rồi mở nhóm mới | Có |

Pseudocode:

```text
integrate(state, element, downstream):
    nextKey = classifier(element)
    if chưa mở nhóm:
        mở nhóm(nextKey, element)
        return true

    if key cũ bằng nextKey:
        thêm element
        return true

    phát snapshot của nhóm cũ
    nếu downstream không nhận thêm:
        đánh dấu nhóm đã đóng
        return false

    mở nhóm mới(nextKey, element)
    return true
```

Nhìn vào điều kiện, ta thấy **không cần giữ toàn bộ dữ liệu nguồn**. Trong quá trình xử lý, Gatherer chỉ giữ **một nhóm đang mở**. Những nhóm trước đã được phát và có thể được pipeline tiếp tục xử lý ngay.

Đồng thời, có một sự đánh đổi: để biết một nhóm đã kết thúc, Gatherer phải **đọc phần tử đầu tiên của nhóm kế tiếp**. Vì thế khi downstream chỉ yêu cầu `limit(1)` nhóm, upstream có thể đã phải xử lý thêm phần tử đầu tiên của nhóm thứ hai để phát được nhóm thứ nhất.

## 6. Finisher: đừng quên nhóm cuối cùng

Giả sử đầu vào là `[A,A,B]`. Khi gặp `B`, integrator phát nhóm `A`. Nhưng sau `B` không còn phần tử mới nào để kích hoạt "khóa đổi", nên nhóm `B` phải được phát ở **finisher**.

```java
(state, downstream) -> {
    if (state.active && !downstream.isRejecting()) {
        downstream.push(new Run<>(
                state.key,
                Collections.unmodifiableList(
                        new ArrayList<>(state.items)
                )
        ));
    }
}
```

Trường hợp **nguồn rỗng**: `active=false`, finisher không phát nhóm giả. Nếu chỉ có một phần tử: finisher phát đúng một nhóm chứa phần tử ấy. Nếu nguồn kết thúc ngay sau lần đổi khóa, finisher phát nhóm mới đang mở.

`downstream.isRejecting()` giúp tránh cố phát thêm khi downstream không muốn nhận đầu ra nữa. Ngoài ra, nếu integrator đã dừng sau khi `push` trả `false`, ta sẽ **đóng nhóm trong trạng thái** để tránh finisher phát lặp.

**Không coi finisher như một lần "xử lý lại" đầu vào:** nó chỉ chốt dữ liệu đã được tích lũy nhưng chưa phát ra. Không nên có thao tác đọc thêm nguồn hoặc quay lại phần tử đã xử lý.

## 7. Chương trình hoàn chỉnh Java 24+: groupConsecutiveBy

Chương trình sau định nghĩa một Gatherer tái sử dụng được, không ràng buộc vào lớp sự kiện cụ thể. `Run<K,T>` biểu diễn một đoạn liên tiếp: khóa và danh sách phần tử của đoạn.

Lưu dưới tên `ConsecutiveKeyGathererDemo.java`, biên dịch và chạy bằng **JDK 24+**.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Gatherer;

public class ConsecutiveKeyGathererDemo {
    record Event(String id, String type, int value) {}
    record Run<K, T>(K key, List<T> items) {}

    static <T, K> Gatherer<T, ?, Run<K, T>> groupConsecutiveBy(
            Function<? super T, ? extends K> classifier) {
        Objects.requireNonNull(classifier, "classifier");

        class State {
            boolean active;
            K key;
            final ArrayList<T> items = new ArrayList<>();
        }

        return Gatherer.ofSequential(
                State::new,

                (state, element, downstream) -> {
                    K nextKey = classifier.apply(element);

                    // Bắt đầu nhóm đầu tiên.
                    if (!state.active) {
                        state.active = true;
                        state.key = nextKey;
                        state.items.add(element);
                        return true;
                    }

                    // Vẫn trong một đoạn liên tiếp.
                    if (Objects.equals(state.key, nextKey)) {
                        state.items.add(element);
                        return true;
                    }

                    // Khóa thay đổi: phát snapshot của đoạn cũ.
                    Run<K, T> completed = new Run<>(
                            state.key,
                            Collections.unmodifiableList(
                                    new ArrayList<>(state.items)
                            )
                    );

                    if (!downstream.push(completed)) {
                        // Downstream không nhận thêm; đừng mở nhóm mới.
                        state.active = false;
                        state.items.clear();
                        return false;
                    }

                    // Bắt đầu một đoạn mới từ phần tử hiện tại.
                    state.key = nextKey;
                    state.items.clear();
                    state.items.add(element);
                    return true;
                },

                (state, downstream) -> {
                    // Chốt đoạn cuối khi nguồn hết.
                    if (state.active && !downstream.isRejecting()) {
                        downstream.push(new Run<>(
                                state.key,
                                Collections.unmodifiableList(
                                        new ArrayList<>(state.items)
                                )
                        ));
                    }
                }
        );
    }

    public static void main(String[] args) {
        List<Event> events = List.of(
                new Event("A1", "A", 10),
                new Event("A2", "A", 20),
                new Event("A3", "A", 30),
                new Event("B1", "B", 40),
                new Event("B2", "B", 50),
                new Event("A4", "A", 60),
                new Event("C1", "C", 70),
                new Event("C2", "C", 80)
        );

        List<Run<String, Event>> runs = events.stream()
                .gather(groupConsecutiveBy(Event::type))
                .toList();

        for (Run<String, Event> run : runs) {
            List<String> ids = run.items().stream()
                    .map(Event::id)
                    .toList();
            System.out.println(run.key() + " -> " + ids);
        }

        // A -> [A1, A2, A3]
        // B -> [B1, B2]
        // A -> [A4]
        // C -> [C1, C2]

        if (runs.size() != 4
                || !runs.get(0).key().equals("A")
                || runs.get(0).items().size() != 3
                || !runs.get(1).key().equals("B")
                || runs.get(1).items().size() != 2
                || !runs.get(2).key().equals("A")
                || runs.get(2).items().size() != 1
                || !runs.get(3).key().equals("C")
                || runs.get(3).items().size() != 2) {
            throw new AssertionError("Nhóm liên tiếp không đúng");
        }

        List<Run<String, Event>> firstTwo = events.stream()
                .gather(groupConsecutiveBy(Event::type))
                .limit(2)
                .toList();

        if (firstTwo.size() != 2
                || !firstTwo.get(0).key().equals("A")
                || !firstTwo.get(1).key().equals("B")) {
            throw new AssertionError("Dừng sớm không đúng");
        }

        System.out.println("PASS");
    }
}
```

Nếu môi trường đã chọn đúng JDK 24 trở lên:

```text
javac ConsecutiveKeyGathererDemo.java
java ConsecutiveKeyGathererDemo
```

Không cần thêm thư viện bên ngoài. Đoạn mã dùng `Stream.gather` và `java.util.stream.Gatherer` đã chính thức trong Java 24. Bài viết **không chạy biên dịch tại STEP 4**; khi áp dụng thật, cần dùng JDK đúng phiên bản và kiểm thử theo build của dự án.

## 8. Vì sao bản cài đặt này đúng?

Xem lại luồng:

```text
Nhận A1: state=A/[A1], chưa phát
Nhận A2: state=A/[A1,A2], chưa phát
Nhận A3: state=A/[A1,A2,A3], chưa phát
Nhận B1: phát A/[A1,A2,A3], state=B/[B1]
Nhận B2: state=B/[B1,B2], chưa phát
Nhận A4: phát B/[B1,B2], state=A/[A4]
Nhận C1: phát A/[A4], state=C/[C1]
Nhận C2: state=C/[C1,C2], chưa phát
Nguồn hết: finisher phát C/[C1,C2]
```

Các tính chất cần kiểm tra:

1. **Đầy đủ:** mỗi phần tử được đưa vào đúng một nhóm, trừ khi downstream chủ động dừng sớm.
2. **Không chồng lấn:** khi khóa đổi, nhóm cũ được phát xong trước khi tạo nhóm mới.
3. **Tối đa:** trong một nhóm không có ranh giới khóa khác; hai nhóm kề nhau không thể có khóa bằng nhau nếu sử dụng cùng một classifier nhất quán.
4. **Giữ thứ tự:** các phần tử trong nhóm giữ encounter order của Stream đầu vào; các nhóm được phát theo đúng trình tự.
5. **Không tự quay lại:** khóa `A` xuất hiện sau đoạn `B` tạo một nhóm `A` mới.
6. **Đóng cuối:** finisher phát nhóm cuối dù không có phần tử kế tiếp.
7. **Không chia sẻ bộ đệm:** mỗi đầu ra chứa snapshot riêng, không bị `clear()` ở nhóm sau làm thay đổi.
8. **Dừng sớm:** nếu downstream từ chối, integrator trả `false` và không cố tiếp tục tạo các nhóm mới.

### Vì sao trả true ở nhánh chưa phát đầu ra?

Integrator trả `true` có nghĩa là **có thể tiếp tục nhận đầu vào**, không phải "đã phát một đầu ra". Khi nhóm đang được tích lũy và chưa đóng, không phát gì vẫn là trường hợp bình thường. Một Gatherer có thể phát 0 hoặc nhiều phần tử cho một phần tử đầu vào.

### Vì sao không dùng state.key == nextKey?

Với khóa kiểu `String`, `new String("A")` và `"A"` có thể là hai object khác tham chiếu nhưng có giá trị bằng nhau. `Objects.equals(state.key, nextKey)` dùng `equals`, đồng thời hỗ trợ khóa `null` nếu chính sách ứng dụng cho phép.

## 9. Xử lý downstream dừng sớm và limit

Ví dụ:

```java
List<Run<String, Event>> firstTwo = events.stream()
        .gather(groupConsecutiveBy(Event::type))
        .limit(2)
        .toList();
```

Trong dữ liệu mẫu, hai nhóm đầu là `A` và `B`. Để phát nhóm `B`, Gatherer phải nhận phần tử `A4` (mốc bắt đầu nhóm thứ ba). Khi đó downstream có thể báo không nhận thêm qua `push`, khiến integrator trả `false`.

Đây là tính chất của **toán tử phụ thuộc ranh giới**: một nhóm chỉ chắc chắn kết thúc khi gặp khóa khác hoặc biết rằng nguồn hết.

```text
Nhận A1,A2,A3: chưa có nhóm hoàn chỉnh
Nhận B1:      phát Run(A)
Nhận B2:      chưa phát Run(B)
Nhận A4:      phát Run(B); limit(2) có đủ kết quả
               -> downstream từ chối thêm
               -> integrator dừng
```

Một chi tiết quan trọng là không nên cho rằng `limit(2)` có nghĩa **chỉ đọc đúng hai phần tử nguồn**. Ở đây giới hạn áp dụng cho **số nhóm đầu ra**, không phải số sự kiện đầu vào.

Ngoài ra, các callback khác trong một pipeline có thể đã xử lý một số phần tử tùy chiến lược thực thi. Vì thế không đặt tác dụng phụ bắt buộc, ví dụ gửi email hoặc ghi tiền, vào classifier để giả định nó sẽ chạy đúng một số lần đoán trước.

### Điều kiện dừng từ integrator

`Integrator.integrate` trả `false` để báo không muốn nhận thêm input. Trong triển khai của ta, điều này xảy ra khi `downstream.push(completed)` trả `false`. Khi đó:

- Không tạo nhóm cho phần tử vừa gây chuyển khóa.
- Đánh dấu `state.active=false` và xóa bộ đệm để tránh phát lại ở finisher.
- Không tái sử dụng trạng thái cho một lần tiêu thụ Stream khác.

Nếu classifier hoặc downstream ném ngoại lệ, ngoại lệ sẽ lan truyền ra terminal operation. Không coi finisher là cơ chế tự động sửa lỗi hoặc bảo đảm rollback tác dụng phụ.

## 10. Nguồn rỗng, một phần tử, null và kiểu khóa

### Nguồn rỗng

```java
List<Run<String, Event>> noRuns =
        java.util.stream.Stream.<Event>empty()
                .gather(groupConsecutiveBy(Event::type))
                .toList();

System.out.println(noRuns.isEmpty()); // true
```

Initializer tạo state với `active=false`, integrator không được gọi và finisher không phát gì.

### Một phần tử

```java
List<Run<String, Event>> oneRun =
        java.util.stream.Stream.of(new Event("E1", "A", 10))
                .gather(groupConsecutiveBy(Event::type))
                .toList();

System.out.println(oneRun.size());            // 1
System.out.println(oneRun.get(0).items().size()); // 1
```

Nhóm đơn được phát ở finisher.

### Khóa null

`Objects.equals` cho phép hai khóa `null` được xem là bằng nhau:

```java
record Label(String text) {}

List<Label> labels = java.util.Arrays.asList(
        new Label(null), new Label(null),
        new Label("X"), new Label(null)
);

List<Run<String, Label>> groups = labels.stream()
        .gather(groupConsecutiveBy(Label::text))
        .toList();

System.out.println(groups.size());  // 3
System.out.println(groups.get(0).key()); // null
System.out.println(groups.get(0).items().size()); // 2
```

Trong hàm dựng Gatherer, `Objects.requireNonNull(classifier)` chỉ kiểm tra **hàm classifier không được null**, không bắt buộc **giá trị khóa trả về** phải khác null. Nếu sản phẩm không chấp nhận khóa null, nên kiểm tra đầu vào hoặc thay bằng giá trị đại diện có ngữ nghĩa rõ ràng.

### Phần tử null

List snapshot từ `Collections.unmodifiableList(new ArrayList<>(...))` có thể chứa phần tử null, nhưng classifier như `Event::type` sẽ ném `NullPointerException` khi nhận `element=null`. Nếu nguồn chứa null, hãy xác định chính sách:

```java
List<Run<String, Event>> safe =
        possiblyNullEvents.stream()
                .filter(Objects::nonNull)
                .gather(groupConsecutiveBy(Event::type))
                .toList();
```

Đoạn này minh họa với biến `possiblyNullEvents` được chuẩn bị ở tầng gọi. **Lọc phần tử null** có thể làm hai đoạn cùng khóa vốn bị ngăn cách bởi phần tử null trở thành liền nhau. Nếu null phải được xem là một **ranh giới**, đừng lọc nó mà hãy định nghĩa khóa/phần tử biểu diễn ranh giới rõ ràng.

## 11. Encounter order là điều kiện quan trọng

Một toán tử nhóm **liên tiếp** phụ thuộc trực tiếp vào encounter order. Với `List.stream()`, thứ tự các phần tử theo List nên có thể xác định duy nhất những ranh giới.

```java
List<String> keys = List.of("A", "A", "B", "A");

List<Run<String, String>> runs = keys.stream()
        .gather(groupConsecutiveBy(Function.identity()))
        .toList();

// Run(A,[A,A]), Run(B,[B]), Run(A,[A])
```

Nhưng nếu nguồn là `HashSet`, thứ tự duyệt **không được cam kết**, nên các đoạn "liên tiếp" không mang một ý nghĩa nghiệp vụ ổn định:

```java
Set<String> unorderedSource =
        new java.util.HashSet<>(List.of("A", "B", "C"));

// Không nên xem kết quả nhóm liên tiếp từ nguồn này
// như những đoạn lịch sử có thứ tự cố định.
```

Nếu dữ liệu có trường `sequence`, `timestamp` hoặc chỉ số, hãy **xác định thứ tự trước khi group**:

```java
List<Event> ordered = events.stream()
        .sorted(Comparator.comparing(Event::id))
        .toList();

List<Run<String, Event>> sortedRuns = ordered.stream()
        .gather(groupConsecutiveBy(Event::type))
        .toList();
```

Lưu ý: comparator theo `id` ở đây chỉ là minh họa kỹ thuật. Với nhật ký thực tế, phải chọn **thời gian, sequence và tie-break** đúng ngữ nghĩa; sắp dữ liệu theo khóa nhóm có thể **thay đổi yêu cầu** bằng cách biến các nhóm tách rời thành một nhóm lớn.

### Đừng gọi unordered() khi cần các đoạn lịch sử

`unordered()` bỏ ràng buộc encounter order. Nó không có nghĩa "xáo trộn" một cách ngẫu nhiên, nhưng khiến một số thao tác không còn phải bảo toàn thứ tự nguồn. Đối với nhóm liên tiếp theo trình tự, bỏ order có thể làm **định nghĩa đầu ra không còn ổn định**.

## 12. Tại sao chưa nên viết combiner song song?

Khó khăn nằm ở ranh giới giữa các phần tách. Ví dụ:

```text
Đầu vào: A A A A B B C

Chia phần việc:
  Trái:  A A A
  Phải:  A B B C

Nhóm cục bộ:
  Trái:  [A,A,A]
  Phải:  [A], [B,B], [C]

Ghép ngây thơ:
  [A,A,A], [A], [B,B], [C]   <- SAI

Ghép đúng:
  [A,A,A,A], [B,B], [C]
```

Để hỗ trợ combiner song song đúng nghĩa, trạng thái của mỗi phân đoạn cần giữ đủ thông tin về **nhóm đầu**, **nhóm cuối** và các nhóm hoàn chỉnh ở giữa. Khi gộp hai phần, phải xét liệu nhóm cuối bên trái có cùng khóa với nhóm đầu bên phải để hợp nhất chúng mà vẫn giữ thứ tự. Đây không còn là phép `List.addAll` đơn giản.

`Gatherer.ofSequential` tránh vấn đề này bằng cách **không cung cấp combiner hỗ trợ chia/gộp trạng thái tại Gatherer**. Nếu pipeline bắt đầu từ `parallelStream()`, không nên cho rằng bước Gatherer này tự nhiên được song song hóa hiệu quả; ràng buộc thứ tự có thể làm giảm lợi ích của xử lý song song.

**Ưu tiên bài học:** viết Gatherer tuần tự chính xác, có test các ranh giới; chỉ thiết kế combiner khi thật sự cần và đã mô hình hóa toán học việc ghép hai phân đoạn, bao gồm đầu/cuối, nhóm rỗng và tính kết hợp (*associativity*).

## 13. Tính trạng thái, non-interference và an toàn bộ nhớ

Gatherer có trạng thái nội bộ **không đồng nghĩa với một pipeline vi phạm stateless/non-interference**. Sự khác biệt là:

- Gatherer dùng **state do initializer tạo riêng cho quá trình đánh giá**, theo hợp đồng của API.
- Classifier nên là hàm **không sửa nguồn**, không ghi vào danh sách hay Map dùng chung.
- Không nên giữ state tích lũy trong một biến global hoặc `static` rồi tái sử dụng qua nhiều lần gọi Stream.
- Downstream phải nhận **snapshot tách biệt** nếu state sẽ bị sửa tiếp.

Ví dụ sai về thiết kế:

```java
static List<Event> sharedBuffer = new ArrayList<>();

// SAI: dùng sharedBuffer làm bộ đệm cho mọi lượt đánh giá
// có thể gây dữ liệu còn sót và race condition.
```

Đúng hơn: tạo bộ đệm trong đối tượng `State` mới được khởi tạo bởi `State::new`.

Một giới hạn khác: các phần tử của `Run` chỉ được **sao chép tham chiếu**, không tự deep-copy. Nếu `Event` chứa những trường mutable như `List<String>` hoặc một object có setter, phần tử vẫn có thể bị sửa từ nơi khác. Với DTO cần bất biến sâu, hãy ánh xạ hoặc sao chép các phần tử thành những giá trị bất biến trước khi gom nhóm.

### Bộ nhớ sử dụng

Với `n` phần tử và đoạn dài nhất có `m` phần tử:

- Bộ đệm tích lũy của Gatherer chứa tối đa khoảng `m` tham chiếu phần tử tại một thời điểm.
- Snapshot một đoạn cần sao chép các tham chiếu của đoạn đó; tổng số tham chiếu được sao chép qua mọi đoạn là `n` nếu tiêu thụ toàn bộ nguồn.
- Bản thân Gatherer không cần giữ lại mọi đoạn đã phát. Nếu gọi `toList()` sau `gather`, **kết quả cuối** vẫn lưu tất cả nhóm và các phần tử của chúng, dùng bộ nhớ tổng thể tăng theo `n`.
- Nếu một đoạn rất dài hoặc nguồn không bao giờ đổi khóa, đầu ra đầu tiên bị trì hoãn và bộ đệm có thể rất lớn.

Với luồng thực sự vô hạn mà khóa không bao giờ đổi, Gatherer này **không thể phát nhóm hoàn chỉnh**. Khi đó cần một quy tắc đóng đoạn khác, chẳng hạn số phần tử tối đa, timeout hoặc cửa sổ thời gian.

## 14. Tổng hợp thống kê cho mỗi đoạn

Vì `gather` trả Stream các `Run`, ta có thể tiếp tục tạo báo cáo:

```java
record RunSummary(
        String type, long count, long totalValue) {}

List<RunSummary> summaries = events.stream()
        .gather(groupConsecutiveBy(Event::type))
        .map(run -> new RunSummary(
                run.key(),
                run.items().size(),
                run.items().stream()
                        .mapToLong(Event::value)
                        .sum()
        ))
        .toList();

summaries.forEach(System.out::println);
```

Kết quả theo dữ liệu mẫu:

```text
RunSummary[type=A, count=3, totalValue=60]
RunSummary[type=B, count=2, totalValue=90]
RunSummary[type=A, count=1, totalValue=60]
RunSummary[type=C, count=2, totalValue=150]
```

Điểm đáng chú ý: có **hai** `RunSummary` với type `A`, vì đây là hai đoạn khác nhau trong dòng sự kiện. Nếu dùng `groupingBy(Event::type, summingLong(...))`, ta sẽ có **một** entry `A` với tổng `120`, làm mất thông tin về các lần quay lại trạng thái `A`.

### Tính số lần chuyển trạng thái

Nếu nguồn không rỗng và mọi lần đổi khóa tạo nhóm mới, thì:

```text
Số lần chuyển khóa = Số nhóm liên tiếp - 1
```

Với ví dụ có 4 nhóm, có 3 lần đổi khóa: `A→B`, `B→A`, `A→C`. Nếu nguồn rỗng, số lần chuyển là 0; trong code có thể dùng `Math.max(0, runs.size() - 1)`.

Khi chỉ cần số lượng nhóm hoặc thống kê tích lũy, có thể phát `RunSummary` thay vì giữ toàn bộ List phần tử; đó là một hướng tối ưu cho dữ liệu lớn sau khi đã nắm vững cơ chế cơ bản.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Hai đoạn cùng khóa nhưng cách xa bị gộp làm một | Dùng `groupingBy` toàn cục | Dùng Gatherer có trạng thái và phát khi khóa đổi. |
| Nhóm cuối cùng bị mất | Chỉ phát trong integrator khi thấy khóa mới | Thêm finisher để flush nhóm còn mở. |
| Kết quả nhóm trước bỗng thành rỗng | Đẩy tham chiếu buffer rồi `clear()` | Tạo snapshot trước khi `push`. |
| Nguồn rỗng nhưng phát một nhóm rỗng | Finisher phát dù chưa mở nhóm | Dùng cờ `active` và chỉ phát khi đúng. |
| Khóa null bị coi là chưa khởi tạo | Dùng `key == null` để xác định state rỗng | Dùng `boolean active` riêng. |
| Hai chuỗi cùng nội dung thành hai nhóm | So sánh khóa bằng `==` | Dùng `Objects.equals` hoặc comparator tương đương đã định nghĩa rõ. |
| Phần tử không còn được tiêu thụ nhưng integrator vẫn chạy | Bỏ qua `downstream.push` trả `false` | Trả `false` từ integrator, tránh mở thêm nhóm. |
| Finisher phát lặp sau khi dừng sớm | Không đóng trạng thái khi downstream từ chối | Đánh dấu `active=false` trước khi trả `false`. |
| Nhóm bị thay đổi khi kết quả đã phát | Phần tử chứa object mutable và bị sửa bên ngoài | Chuyển sang giá trị bất biến/deep-copy nếu nghiệp vụ cần. |
| Thứ tự nhóm không ổn định | Nguồn unordered hoặc bỏ order | Xác lập encounter order theo sự kiện trước khi gather. |
| Chạy song song cho nhóm sai ở ranh giới phân đoạn | Combiner chỉ nối hai danh sách nhóm | Thiết kế combiner có xử lý hai nhóm giáp ranh, hoặc dùng `ofSequential`. |
| Tốn nhiều bộ nhớ khi một khóa kéo dài | Bộ đệm giữ toàn bộ đoạn chưa đóng | Đặt quy tắc chia đoạn phụ, dùng đầu ra tổng hợp hoặc giới hạn đầu vào. |
| Code không biên dịch trên JDK 17/21 | `Stream.gather` chưa là API chuẩn ở phiên bản đó | Dùng JDK 24+ hoặc giải pháp tuần tự khác phù hợp phiên bản. |

## 16. Bài tập thực hành và lời giải

### Bài 1 — Đếm những đoạn liên tiếp

Cho dãy:

```java
List<String> values =
        List.of("X", "X", "Y", "X", "X", "Z", "Z", "Z");
```

**Yêu cầu:** nhóm các phần tử liên tiếp và cho biết số nhóm, số phần tử trong mỗi nhóm, số lần chuyển khóa.

**Lời giải tham khảo:**

```java
List<Run<String, String>> runs = values.stream()
        .gather(groupConsecutiveBy(Function.identity()))
        .toList();

List<Integer> lengths = runs.stream()
        .map(run -> run.items().size())
        .toList();

System.out.println(lengths); // [2, 1, 2, 3]
System.out.println(runs.size()); // 4
System.out.println(Math.max(0, runs.size() - 1)); // 3
```

### Bài 2 — Phân nhóm số theo dấu chẵn lẻ

Cho:

```java
List<Integer> numbers =
        List.of(2, 4, 7, 9, 12, 5, 3, 8);
```

**Yêu cầu:** gom từng đoạn liên tiếp có cùng tính chẵn/lẻ.

```java
List<Run<Boolean, Integer>> parityRuns = numbers.stream()
        .gather(groupConsecutiveBy(n -> n % 2 == 0))
        .toList();

parityRuns.forEach(run ->
        System.out.println(run.key() + " -> " + run.items()));

// true  -> [2, 4]
// false -> [7, 9]
// true  -> [12]
// false -> [5, 3]
// true  -> [8]
```

### Bài 3 — Kiểm thử nguồn rỗng, một phần tử và nhóm cuối

**Yêu cầu:** tạo ba bộ test:

1. Nguồn rỗng → 0 nhóm.
2. Một phần tử `A` → một nhóm chứa `A`.
3. `[A, A, B]` → hai nhóm; nhóm `B` phải được finisher phát ra.

```java
List<Run<String, String>> empty =
        java.util.stream.Stream.<String>empty()
                .gather(groupConsecutiveBy(Function.identity()))
                .toList();

List<Run<String, String>> single =
        java.util.stream.Stream.of("A")
                .gather(groupConsecutiveBy(Function.identity()))
                .toList();

List<Run<String, String>> lastRun =
        java.util.stream.Stream.of("A", "A", "B")
                .gather(groupConsecutiveBy(Function.identity()))
                .toList();

System.out.println(empty.size()); // 0
System.out.println(single.get(0).items()); // [A]
System.out.println(lastRun.get(1).items()); // [B]
```

### Bài 4 — Kiểm thử snapshot và dừng sớm

**Yêu cầu:** lấy kết quả từ `[A,A,B,B,C]` rồi xác nhận:

- Mỗi danh sách nhóm vẫn giữ giá trị sau khi các nhóm sau được xử lý.
- Không thể thêm vào List snapshot.
- `limit(2)` chỉ phát hai nhóm hoàn chỉnh.

```java
List<String> data = List.of("A", "A", "B", "B", "C");

List<Run<String, String>> all = data.stream()
        .gather(groupConsecutiveBy(Function.identity()))
        .toList();

System.out.println(all.get(0).items()); // [A, A]
System.out.println(all.get(1).items()); // [B, B]
System.out.println(all.get(2).items()); // [C]

// all.get(0).items().add("X");
// UnsupportedOperationException

List<Run<String, String>> firstTwo = data.stream()
        .gather(groupConsecutiveBy(Function.identity()))
        .limit(2)
        .toList();

System.out.println(firstTwo.size()); // 2
```

### Bài 5 — Tính tổng từng đoạn mà không gộp toàn cục

**Yêu cầu:** với dãy sự kiện `A(10), A(20), B(7), A(5)`, tính tổng cho **từng đoạn** theo đúng thứ tự.

```java
List<Event> input = List.of(
        new Event("E1", "A", 10),
        new Event("E2", "A", 20),
        new Event("E3", "B", 7),
        new Event("E4", "A", 5)
);

List<String> totals = input.stream()
        .gather(groupConsecutiveBy(Event::type))
        .map(run -> run.key() + ":" + run.items().stream()
                .mapToInt(Event::value)
                .sum())
        .toList();

System.out.println(totals); // [A:30, B:7, A:5]
```

### Bài 6 — Phân tích trường hợp đặc biệt

Hãy trả lời:

1. Nếu khóa `A` xuất hiện lần nữa sau khóa `B`, tại sao phải tạo nhóm `A` mới?
2. Nếu classifier trả về `null` cho hai phần tử liên tiếp, cờ `active` giúp gì?
3. Nếu gọi `sorted(Comparator.comparing(Event::type))` trước Gatherer, kết quả có còn biểu diễn các đoạn liên tiếp **theo lịch sử ban đầu** không?
4. Vì sao combiner chỉ `addAll` hai danh sách nhóm không đúng khi hai phân đoạn có chung khóa ở ranh giới?
5. Nếu nguồn là một Stream vô hạn toàn phần tử khóa `A`, Gatherer có phát được một nhóm hoàn chỉnh đầu tiên không?

**Định hướng trả lời:** (1) vì có ranh giới `B` ở giữa; (2) phân biệt "chưa bắt đầu" và "khóa thực tế bằng null"; (3) không, thứ tự đã bị thay đổi; (4) phải hợp nhất nhóm cuối bên trái và nhóm đầu bên phải nếu cùng khóa; (5) không, trừ khi thiết kế thêm điều kiện đóng nhóm.

## 17. Checklist trước khi sử dụng trong dự án

1. **Phiên bản:** dùng JDK 24+ cho API chính thức của `Stream.gather` và `Gatherer`.
2. **Hợp đồng khóa:** classifier có stateless, không can thiệp nguồn và quy tắc bằng nhau rõ ràng không?
3. **Encounter order:** nguồn có thứ tự theo nghiệp vụ chưa? Có chỗ nào gọi `unordered()` không?
4. **Trạng thái mới:** initializer có tạo một state độc lập cho mỗi lượt đánh giá không?
5. **Nhóm đầu:** phần tử đầu có mở nhóm mà không tạo nhóm rỗng không?
6. **Cùng khóa:** phần tử có được thêm đúng một lần vào bộ đệm không?
7. **Đổi khóa:** nhóm cũ có được phát trước khi bắt đầu nhóm mới không?
8. **Snapshot:** kết quả đã tách khỏi bộ đệm sẽ bị tái sử dụng chưa?
9. **Finisher:** nhóm cuối có được phát, còn nguồn rỗng có không phát gì không?
10. **Dừng sớm:** integrator có kiểm tra `push` trả false và ngừng đúng cách không?
11. **Null:** khóa null và phần tử null có chính sách rõ ràng không?
12. **Song song:** đã giải thích vì sao dùng `ofSequential`, không triển khai combiner sai chưa?
13. **Tài nguyên:** với nguồn I/O, đã đóng Stream bằng `try-with-resources` thích hợp chưa?
14. **Bộ nhớ:** đoạn dài nhất có thể lớn bao nhiêu? Có cần giới hạn thời gian/số phần tử không?
15. **Kiểm thử:** đã kiểm nguồn rỗng, một phần tử, khóa quay lại, nhiều nhóm, limit, snapshot và đầu vào ordered/unordered chưa?

## Ghi nhớ

Toán tử **gộp phần tử liên tiếp theo khóa** khác hẳn `Collectors.groupingBy`: chỉ những phần tử **kề nhau trong encounter order** và có khóa bằng nhau mới thuộc cùng một nhóm. Một khóa có thể xuất hiện ở nhiều nhóm nếu đã bị khóa khác ngắt quãng.

Với **Java 24+**, `Gatherer.ofSequential` là điểm khởi đầu phù hợp để tự viết toán tử này. **Initializer** tạo trạng thái nhóm đang mở; **integrator** thêm phần tử hoặc phát nhóm cũ khi khóa đổi; **finisher** phát nhóm cuối khi nguồn kết thúc. Luôn sao chép bộ đệm trước `downstream.push`, tuân thủ tín hiệu từ chối của downstream và giữ classifier không can thiệp nguồn.

Khi đã đảm bảo đúng ranh giới, thứ tự, dừng sớm và trạng thái, mới cân nhắc tối ưu bộ nhớ hoặc thiết kế combiner song song. Trong trường hợp nhóm quá dài hoặc luồng không đổi khóa vô hạn, cần thêm điều kiện đóng nhóm thay vì chờ một ranh giới sẽ không bao giờ đến.
