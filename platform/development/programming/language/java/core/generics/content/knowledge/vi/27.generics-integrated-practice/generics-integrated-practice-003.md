# Thiết kế hàm sao chép đúng PECS trong Java Generics

Một thao tác rất phổ biến khi thiết kế API Java là **đọc phần tử từ một nguồn và ghi chúng vào một đích**. Nếu chỉ khai báo `List<T>` ở cả hai phía, API có thể trở nên quá hẹp: bạn muốn đọc `Integer` từ `List<Integer>` rồi ghi vào `List<Number>`, nhưng **Java Generics là bất biến** (*invariant*), nên `List<Integer>` không phải subtype của `List<Number>`.

Giải pháp đúng là chọn wildcard theo **vai trò của từng tham số**:

> **PECS = Producer Extends, Consumer Super.** Bên *sản xuất* phần tử để ta đọc dùng `? extends T`; bên *tiêu thụ* phần tử ta muốn ghi dùng `? super T`.

Một chữ ký điển hình:

```java
static <T> int appendAll(
        Iterable<? extends T> source,
        Collection<? super T> destination)
```

Nó nói rằng **nguồn cung cấp các phần tử có thể đọc như `T`** và **đích chấp nhận các phần tử `T`**. Method có thể làm việc với `List<Integer>` → `List<Number>`, `List<Integer>` → `List<Object>`, đồng thời không cần raw types hoặc unchecked casts.

Tuy nhiên, chữ “sao chép” có thể chỉ **hai hợp đồng khác nhau**:

- **Append:** duyệt nguồn rồi thêm phần tử vào đích, thường dùng `Collection.add`. Đích có thể tăng kích thước hoặc, với `Set`, không tăng vì phần tử đã tồn tại.
- **Overwrite/replace:** ghi đè các vị trí đang có trong một `List`, thường dùng `List.set`. Đích phải có đủ vị trí; thao tác không tự thêm chỗ mới.

Bài thực hành này xây cả hai loại, minh họa bản sao tạm để xử lý vùng dữ liệu chồng lấn, và giải thích giới hạn runtime như `null`, mutation, alias, partial failure và concurrent modification.

## 1. Mục tiêu và kiến thức nền

Sau bài, bạn có thể:

1. Tự giải thích tại sao `List<Integer>` không gán được cho `List<Number>`, dù `Integer extends Number`.
2. Chọn **`Iterable<? extends T>` cho nguồn** và **`Collection<? super T>` cho đích** khi một thao tác đọc nguồn–ghi đích.
3. Xây một method `appendAll` không dùng cast, có số phần tử đã xử lý rõ nghĩa.
4. Xây một method `overwritePrefix` sử dụng `List.set`, kiểm tra kích thước đích và snapshot nguồn để hạn chế lỗi khi các list views chồng lấn.
5. Phân biệt `Collections.copy` với `Collection.addAll`/tự viết method append.
6. Biết khi nào dùng `List<T>`, `List<?>`, `? extends T`, `? super T` hay `<T>` riêng ở method.
7. Mở rộng sang sao chép **kèm biến đổi kiểu** với `Function<? super S,? extends R>`.
8. Viết Javadoc, bài test và tài liệu hóa những điều generic signature **không tự bảo đảm**: mutability, null policy, atomicity, aliasing, thứ tự và đa luồng.

Bài sử dụng Java 17 trở lên, không cần thư viện ngoài JDK.

## 2. Vì sao `List<T>` ở cả hai phía chưa đủ linh hoạt?

Xét cách viết ban đầu:

```java
static <T> void copyTooNarrow(
        List<T> source,
        List<T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
```

Method có thể hoạt động khi hai tham số có type arguments tương thích với cùng `T`, nhưng lời gọi với `List<Integer>` và `List<Number>` **không được `copyTooNarrow` diễn đạt một cách tự nhiên** khi suy luận trực tiếp theo invariant `List<T>`.

```java
List<Integer> ints = List.of(1, 2, 3);
List<Number> numbers = new ArrayList<>();

// copyTooNarrow(ints, numbers); // Không suy luận được T chung phù hợp
```

`List<Integer>` không phải `List<Number>`. Nếu phép gán ấy được cho phép, code dùng tham chiếu `List<Number>` có thể thêm `Double` vào một list vốn được nhìn dưới kiểu `List<Integer>`:

```java
// Đoạn giả định KHÔNG hợp lệ trong Java:
// List<Number> aliases = ints;
// aliases.add(3.14); // Phá hợp đồng List<Integer>
```

**Giải pháp không phải `(List<Number>)(List<?>)ints`**. Cast unchecked làm mất tính an toàn mà compiler đang cố bảo vệ. Hãy để phương thức nói rõ **chỉ đọc** từ nguồn và **chỉ ghi** vào đích bằng wildcard ở đúng vị trí.

## 3. Đọc PECS từ góc nhìn producer và consumer

Cho `T = Integer`:

```java
List<Integer> integers = List.of(2, 4, 6);

List<? extends Number> producer = integers;
Number first = producer.get(0); // Đọc được như Number.

// producer.add(8); // Không biên dịch với non-null Integer thông thường.

List<? super Integer> consumer = new ArrayList<Number>();
consumer.add(9); // Ghi Integer hợp lệ.
Object item = consumer.get(0); // Đọc an toàn ít nhất như Object.
```

Hai wildcard có ý nghĩa khác nhau:

| Kiểu tham chiếu | Dùng để làm gì? | Đọc | Ghi |
| --- | --- | --- | --- |
| `List<T>` | Biết element type `T` ở tham chiếu | `T` | `T` |
| `List<? extends T>` | **Producer** của các giá trị đọc được như `T` | `T` | Không thêm một giá trị `T` non-null tùy ý |
| `List<? super T>` | **Consumer** có thể nhận `T` | `Object` nếu không biết kiểu đích cụ thể hơn | `T` |
| `List<?>` | Không cần biết element type | `Object` | Không thêm giá trị non-null tùy ý |

Ghi chú kỹ thuật: một số thao tác như thêm `null` có thể được compiler chấp nhận qua wildcard, nhưng **đó không phải lý do chọn kiểu nguồn** và còn phụ thuộc null policy của collection. Khi học PECS, hãy hiểu “không thêm được phần tử `T` tùy ý qua `? extends T`”, tránh phát biểu tuyệt đối rằng bất kỳ thao tác `add` nào cũng bị cấm.

**Wildcard không quy định mutability runtime.** Một tham chiếu `List<? super Integer>` vẫn có thể trỏ tới một list không hỗ trợ `add`, và lời gọi hợp kiểu có thể ném `UnsupportedOperationException`.

## 4. Chữ ký cốt lõi của phép append

Thiết kế:

```java
static <T> int appendAll(
        Iterable<? extends T> source,
        Collection<? super T> destination) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(destination, "destination");

    int processed = 0;
    for (T value : source) {
        destination.add(value);
        processed++;
    }
    return processed;
}
```

Giải thích từng phần:

- `<T>` là **type parameter của method**, liên kết element type được đọc từ nguồn với element type được đích chấp nhận.
- `Iterable<? extends T>` nói rằng nguồn có thể là `List<Integer>`, `Set<Integer>` hoặc một iterable khác tạo ra các giá trị phù hợp với `T`. Ta chỉ cần thao tác lặp nên không bắt nguồn phải là `List`.
- `Collection<? super T>` nói rằng destination có thể nhận các phần tử `T`. Nó không ép destination phải là `List<T>` đúng chính xác.
- `for (T value : source)` đọc an toàn: phần tử của nguồn là một subtype phù hợp của `T`.
- `destination.add(value)` ghi an toàn: destination chấp nhận `T` hoặc supertype tương ứng.
- `processed` **tăng sau mỗi lần `add` trả về bình thường** và không có exception. Nó không phải số phần tử mới thực sự được thêm với mọi loại `Collection`.

Ví dụ:

```java
List<Integer> integers = List.of(2, 4, 6);
List<Number> numbers = new ArrayList<>(List.of(0.5));

int count = appendAll(integers, numbers);
System.out.println(count);   // 3
System.out.println(numbers); // [0.5, 2, 4, 6]
```

Compiler kiểm tra đúng quan hệ `Integer <: Number` thông qua wildcard mà không cần raw type.

### Vì sao chọn `Iterable` và `Collection` thay vì hai `List`?

Hàm này **chỉ đọc tuần tự**, không cần `get(i)` hay `set(i)` ở nguồn. Đích chỉ cần hỗ trợ `add`, không cần truy cập chỉ số. Do đó việc dùng `Iterable` cho nguồn và `Collection` cho đích giảm ràng buộc API không cần thiết.

Nếu nghiệp vụ chỉ cho phép sao chép từ `List` đến `List` vì yêu cầu order, size hoặc random access, chữ ký hẹp hơn có thể hợp lý. Hãy chọn abstraction **theo thao tác thực tế**, không phải theo thói quen viết `List<T>` ở mọi nơi.

## 5. `appendAll` chấp nhận những cặp kiểu nào?

Hãy xem các lời gọi:

```java
List<Integer> ints = List.of(1, 2);
Collection<Number> numbers = new ArrayList<>();
Collection<Object> objects = new ArrayList<>();

appendAll(ints, numbers); // Đúng: Number tiêu thụ được Integer.
appendAll(ints, objects); // Đúng: Object tiêu thụ được Integer.
```

Một bộ lưu subtype cũng có thể làm nguồn khi kết quả được đích cho phép. Ví dụ:

```java
List<Double> doubles = List.of(2.5, 4.5);
Collection<Number> numbers = new ArrayList<>();
appendAll(doubles, numbers); // Đúng.
```

Ngược lại:

```java
List<Number> source = List.of(1, 2.5);
List<Integer> target = new ArrayList<>();

// appendAll(source, target); // Không biên dịch: đích không nhận mọi Number.
```

Nếu lời gọi cuối được cho phép, phần tử `Double` ở nguồn có thể bị ghi vào `List<Integer>`, trái hợp đồng typed của đích.

**Không nên chữa lỗi bằng unchecked cast.** Trường hợp này là dữ liệu hoặc thiết kế hướng sao chép không tương thích; hãy chuyển dữ liệu có kiểm tra/biến đổi (ví dụ làm tròn theo chính sách domain) hoặc chọn kiểu đích rộng hơn.

## 6. `Collection.add` có thể không thêm phần tử mới

Trong `Collection<E>`, `add(E)` trả một `boolean` cho biết collection **đã thay đổi vì lời gọi đó** theo hợp đồng của phương thức. Đối với `List` mutable, thêm một phần tử thường làm size tăng; đối với `Set`, một phần tử đã tồn tại có thể khiến `add` trả `false`.

Ví dụ:

```java
List<Integer> source = List.of(2, 4, 6);
Set<Number> unique = new LinkedHashSet<>(List.of(2, 4));

int processed = appendAll(source, unique);

System.out.println(processed); // 3
System.out.println(unique);    // [2, 4, 6]
```

Dù chỉ phần tử 6 tạo ra một entry mới, `processed == 3` vì method **đã xử lý thành công ba lần gọi `add`**, kể cả những lần `add` trả `false`.

Nếu hợp đồng muốn trả **số lần `add` thực sự thay đổi collection**, hãy viết một method hoặc một tên rõ hơn:

```java
static <T> int countAccepted(
        Iterable<? extends T> source,
        Collection<? super T> destination) {
    int accepted = 0;
    for (T value : source) {
        if (destination.add(value)) {
            accepted++;
        }
    }
    return accepted;
}
```

Hai cách đếm trả về giá trị khác nhau trên `Set` có phần tử trùng. Không nên viết Javadoc “number of inserted elements” cho method `appendAll` đang thực sự đếm **các phần tử đã xử lý**.

## 7. Append khác overwrite: đích `List` với các vị trí có sẵn

Một số bài toán “copy” không muốn **thêm** mà muốn **ghi đè** các vị trí hiện có. Thư viện Java cung cấp:

```java
Collections.copy(destination, source);
```

Chữ ký generic có dạng:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

`src` là producer; `dest` là consumer. Đây chính là PECS. Nhưng **hợp đồng runtime khác `appendAll`**:

- `Collections.copy` thay thế các vị trí đầu của `dest` bằng phần tử từ `src`.
- `dest` phải có **ít nhất** `src.size()` phần tử đang tồn tại.
- `dest` cần hỗ trợ `set` ở các vị trí được ghi; một `List.of` unmodifiable không đáp ứng.
- Nếu `dest` dài hơn nguồn, các phần tử còn lại vẫn được giữ.
- Nếu `dest` quá ngắn, `IndexOutOfBoundsException` có thể xảy ra.
- Một số live views/chồng lấn có thể khiến kết quả copy trực tiếp khác mong đợi; cần xét alias semantics.

Ví dụ:

```java
List<Integer> src = List.of(2, 4, 6);
List<Number> dest = new ArrayList<>(List.of(-1, -1, -1, -1));

Collections.copy(dest, src);
System.out.println(dest); // [2, 4, 6, -1]
```

Cần phân biệt với:

```java
dest.addAll(src); // Thêm ba phần tử vào cuối; không thay ba ô đầu.
```

**Đừng dùng `new ArrayList<>(capacity)` rồi gọi `Collections.copy` ngay.** Capacity chỉ là khả năng cấp phát nội bộ; list mới có `size()==0`. Bạn phải tạo **các phần tử đang tồn tại** đủ số lượng hoặc dùng append thay vì overwrite.

## 8. Xây `overwritePrefix`: kiểm tra độ dài và snapshot nguồn

Tự viết một biến thể an toàn hơn với **source/destination là hai subList views chồng lấn**:

```java
static <T> int overwritePrefix(
        List<? super T> destination,
        List<? extends T> source) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(destination, "destination");

    // Sao chép nguồn trước khi sửa đích, tránh ghi đè dữ liệu
    // còn cần đọc khi hai list views cùng backing storage.
    List<T> snapshot = new ArrayList<>(source);

    if (destination.size() < snapshot.size()) {
        throw new IndexOutOfBoundsException(
                "destination too short: "
                + destination.size() + " < " + snapshot.size());
    }

    for (int i = 0; i < snapshot.size(); i++) {
        destination.set(i, snapshot.get(i));
    }

    return snapshot.size();
}
```

**Hai lựa chọn thiết kế nổi bật:**

1. **Snapshot nguồn trước khi ghi** để nếu source và destination chia sẻ backing list, việc ghi vào destination không làm biến đổi những phần tử còn cần đọc của source trong quá trình copy.
2. **Kiểm tra số lượng vị trí trước khi bắt đầu ghi** để một destination quá ngắn bị từ chối mà không có các lần `set` đã thực hiện từ vòng lặp này.

Ví dụ:

```java
List<Integer> source = List.of(2, 4, 6);
List<Number> slots = new ArrayList<>(List.of(-1, -1, -1, -1));

int n = overwritePrefix(slots, source);
System.out.println(n);     // 3
System.out.println(slots); // [2, 4, 6, -1]
```

**Không phải transaction atomic:** nếu destination không hỗ trợ `set`, một phần `set` từ chối, hoặc có side effects/đồng thời từ caller khác, có thể đã có một số vị trí được ghi trước khi lỗi phát sinh. Kiểm tra size từ đầu chỉ bảo đảm **không thất bại vì chiều dài ban đầu không đủ** trong tình huống không có thay đổi cạnh tranh.

### Kích thước nhỏ hơn nguồn

```java
List<Number> tooSmall = new ArrayList<>(List.of(-1, -1));

try {
    overwritePrefix(tooSmall, List.of(2, 4, 6));
} catch (IndexOutOfBoundsException expected) {
    System.out.println("Destination too short");
}

System.out.println(tooSmall); // [-1, -1]
```

Hàm tạo snapshot, so độ dài **trước mọi lần `set`**, nên trong ví dụ single-threaded này đích giữ nguyên. `Collections.copy` cũng yêu cầu đủ độ dài nhưng không có cùng lời hứa về snapshot/aliasing như biến thể tự viết.

## 9. Lỗi thường gặp khi dùng `Collections.copy`

Một đoạn trông hợp lý nhưng sai:

```java
List<Integer> source = List.of(1, 2, 3);
List<Number> destination = new ArrayList<>(source.size());

// KHÔNG hỗ trợ vì destination hiện vẫn có size = 0:
// Collections.copy(destination, source);
```

Constructor `ArrayList<>(initialCapacity)` chỉ đặt **capacity**, không tạo phần tử. Hai lựa chọn:

```java
// Nếu muốn thêm:
destination.addAll(source);
```

hoặc:

```java
// Nếu muốn ghi đè từng ô đã tồn tại:
List<Number> destination = new ArrayList<>(
        Arrays.asList(0, 0, 0));
Collections.copy(destination, source);
```

Còn một vấn đề: `List.of` không hỗ trợ `set`; `Arrays.asList` có **kích thước cố định nhưng cho phép `set`**. Bởi vậy:

```java
List<Number> fixed = Arrays.<Number>asList(-1, -1, -1);
Collections.copy(fixed, source); // Hợp lệ khi phần tử/size phù hợp.
```

Trong khi:

```java
List<Number> unmodifiable = List.of(-1, -1, -1);
// Collections.copy(unmodifiable, source); // Có thể ném UnsupportedOperationException.
```

Dấu ngoặc chú thích không phải do code không biên dịch: lời gọi có kiểu hợp lệ nhưng implementation từ chối sửa đổi **ở runtime**.

## 10. Self-copy và vùng `subList` chồng lấn

Một lỗi khó thấy trong các thuật toán sao chép là **nguồn và đích tham chiếu cùng cấu trúc dữ liệu**.

### 10.1. Append một list vào chính nó

```java
List<Integer> list = new ArrayList<>(List.of(1, 2, 3));

// Không nên mặc định thao tác duyệt source đồng thời add vào
// chính collection là an toàn:
// appendAll(list, list);
```

Trong một `ArrayList` thông thường, vòng lặp `for-each` sử dụng iterator. Thay đổi cấu trúc list qua `add` trong lúc đang duyệt có thể gây `ConcurrentModificationException`. Với một số iterable/concurrent collection khác, cách duyệt và kết quả có thể khác; không được giả định “mọi self-copy sẽ luôn ném một exception cụ thể”.

Một cách có chủ đích là **snapshot trước khi append**:

```java
static <T> int appendSnapshot(
        Iterable<? extends T> source,
        Collection<? super T> destination) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(destination, "destination");

    List<T> snapshot = new ArrayList<>();
    for (T value : source) {
        snapshot.add(value);
    }

    for (T value : snapshot) {
        destination.add(value);
    }
    return snapshot.size();
}
```

Với:

```java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3));
appendSnapshot(values, values);

System.out.println(values); // [1, 2, 3, 1, 2, 3]
```

Nguồn được duyệt xong **trước khi** đích thay đổi, nên việc self-append này có hành vi dễ dự đoán hơn trong trường hợp single-threaded. Snapshot tiêu tốn bộ nhớ **O(n)** theo số phần tử nguồn, và không tự bảo đảm một bản chụp đồng bộ nếu nguồn bị thread khác sửa trong khi snapshot đang được xây dựng.

### 10.2. Hai `subList` views dùng chung backing list

```java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));

List<Integer> source = values.subList(0, 3);
List<Integer> target = values.subList(1, 4);

overwritePrefix(target, source);

System.out.println(values); // [1, 1, 2, 3]
```

Nếu một thuật toán đọc–ghi xen kẽ trực tiếp trên hai views, lần ghi vào target có thể thay đổi phần tử mà vòng lặp sắp đọc từ source; với views chồng lấn, đó là một dependency không được tính đến. Trong `overwritePrefix`, `snapshot` chứa `[1,2,3]` trước khi có ghi nào, nên phần được sao chép có nghĩa rõ ràng.

**Đừng tuyên bố đây là snapshot thread-safe/atomic**. Trong multi-threaded code, quá trình tạo snapshot và các lệnh `set` vẫn cần chính sách đồng bộ nếu phải quan sát dữ liệu nhất quán.

## 11. So sánh ba chiến lược sao chép

| Chiến lược | Nguồn | Đích | Thao tác chính | Điều kiện và trade-off |
| --- | --- | --- | --- | --- |
| `appendAll` | `Iterable<? extends T>` | `Collection<? super T>` | `add` theo vòng lặp | Có thể thay kích thước; không tự an toàn cho self-append |
| `appendSnapshot` | `Iterable<? extends T>` | `Collection<? super T>` | Snapshot rồi `add` | Thêm bộ nhớ O(n); tự sao chép dễ dự đoán hơn |
| `overwritePrefix` | `List<? extends T>` | `List<? super T>` | Snapshot rồi `set` | Cần `dest.size >= src.size`, hỗ trợ `set`; tránh lỗi đọc–ghi chồng lấn |
| `Collections.copy` | `List<? extends T>` | `List<? super T>` | Thay phần tử đã tồn tại | Có sẵn trong JDK; cần đủ vị trí, xem contract về views/mutation |
| `destination.addAll(source)` | `Collection<? extends E>` | `Collection<E>` | Thêm hàng loạt theo API collection | Tiện nếu đã có collection phù hợp; hợp đồng riêng về self-add và failure |

**Độ phức tạp** phụ thuộc implementation. Với ArrayList, append tuần tự thường có tổng thời gian O(n) theo mô hình amortized capacity; snapshot cũng mất O(n) bộ nhớ; với LinkedList hoặc custom Collection, chi phí có thể khác. Không bảo đảm `Collection.add`, `List.get`, `List.set` đều O(1) đối với mọi implementation.

Nếu cần **thêm** và nguồn là `Collection<? extends T>`, thường dùng `destination.addAll(source)` là đủ. Nếu API cần nhận bất kỳ `Iterable` nào, đếm phần tử đã xử lý, điều khiển validation/exception hoặc snapshot trước mutation, helper tự viết có giá trị riêng.

## 12. Generic method mở rộng: copy kèm chuyển đổi kiểu `S -> R`

PECS cũng áp dụng khi giá trị đầu vào và đầu ra **không cùng một kiểu**.

```java
static <S,R> int mapAppend(
        Iterable<? extends S> source,
        Collection<? super R> destination,
        Function<? super S, ? extends R> mapper) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(destination, "destination");
    Objects.requireNonNull(mapper, "mapper");

    int processed = 0;
    for (S value : source) {
        destination.add(mapper.apply(value));
        processed++;
    }
    return processed;
}
```

Ở đây:

- `S` là **source element type**, `R` là **result element type**.
- `Iterable<? extends S>` sản xuất những giá trị có thể đọc như `S`.
- `Function<? super S, ? extends R>` **tiêu thụ `S`** và **sản xuất `R`**.
- `Collection<? super R>` tiêu thụ kết quả `R`.

Ví dụ:

```java
List<Integer> ints = List.of(2, 4, 6);
List<Number> halves = new ArrayList<>();

mapAppend(ints, halves, n -> n / 2.0);

System.out.println(halves); // [1.0, 2.0, 3.0]
```

Vì mapper trả `Double`, kiểu đích `Number` đủ rộng để nhận kết quả. Không cần ép `Integer` thành `Double` bằng unchecked cast; phép chia thực hiện thông qua biểu thức số thông thường.

**Lưu ý contract:** nếu mapper ném exception hoặc destination từ chối `add`, một số phần tử trước đó có thể đã được ghi. Nếu mapper trả null, khả năng ghi null phụ thuộc đích; API có thể chủ động cấm bằng `requireNonNull` nếu yêu cầu nghiệp vụ đòi vậy.

## 13. Bản demo Java 17+ hoàn chỉnh

Lưu tệp **`PecsCopyDemo.java`**. Chương trình có đủ bốn helper và nhiều tình huống kiểm chứng PECS, append, overwrite, overlap, size, Set và destination không sửa được.

```java
import java.util.*;
import java.util.function.Function;

public class PecsCopyDemo {
    static <T> int appendAll(
            Iterable<? extends T> source,
            Collection<? super T> destination) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");

        int processed = 0;
        for (T value : source) {
            destination.add(value);
            processed++;
        }
        return processed;
    }

    static <T> int appendSnapshot(
            Iterable<? extends T> source,
            Collection<? super T> destination) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");

        List<T> snapshot = new ArrayList<>();
        for (T value : source) {
            snapshot.add(value);
        }
        for (T value : snapshot) {
            destination.add(value);
        }
        return snapshot.size();
    }

    static <T> int overwritePrefix(
            List<? super T> destination,
            List<? extends T> source) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");

        List<T> snapshot = new ArrayList<>(source);
        if (destination.size() < snapshot.size()) {
            throw new IndexOutOfBoundsException(
                    "destination too short: " + destination.size()
                    + " < " + snapshot.size());
        }

        for (int i = 0; i < snapshot.size(); i++) {
            destination.set(i, snapshot.get(i));
        }
        return snapshot.size();
    }

    static <S,R> int mapAppend(
            Iterable<? extends S> source,
            Collection<? super R> destination,
            Function<? super S, ? extends R> mapper) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");
        Objects.requireNonNull(mapper, "mapper");

        int processed = 0;
        for (S value : source) {
            destination.add(mapper.apply(value));
            processed++;
        }
        return processed;
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(2, 4, 6);
        List<Number> numbers =
                new ArrayList<>(List.of(0.5));

        System.out.println("Append count: "
                + appendAll(integers, numbers));
        System.out.println("Numbers: " + numbers);

        List<Object> objects = new ArrayList<>();
        appendAll(integers, objects);
        System.out.println("Objects: " + objects);

        List<Number> slots =
                new ArrayList<>(List.of(-1, -1, -1, -1));
        System.out.println("Replaced count: "
                + overwritePrefix(slots, integers));
        System.out.println("Slots: " + slots);

        List<Number> tooSmall =
                new ArrayList<>(List.of(-1, -1));
        try {
            overwritePrefix(tooSmall, integers);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println(
                    "Too small: IndexOutOfBoundsException");
        }
        System.out.println(
                "Too small unchanged: " + tooSmall);

        List<Integer> same =
                new ArrayList<>(List.of(1, 2, 3));
        System.out.println("Self-copy count: "
                + appendSnapshot(same, same));
        System.out.println("Self-copy: " + same);

        List<Integer> overlap =
                new ArrayList<>(List.of(1, 2, 3, 4));
        overwritePrefix(
                overlap.subList(1, 4),
                overlap.subList(0, 3));
        System.out.println("Overlapping views: " + overlap);

        List<Number> mapped = new ArrayList<>();
        System.out.println("Mapped count: "
                + mapAppend(integers, mapped, n -> n / 2.0));
        System.out.println("Mapped: " + mapped);

        Set<Number> unique =
                new LinkedHashSet<>(List.of(2, 4));
        System.out.println("Set processed: "
                + appendAll(integers, unique));
        System.out.println("Set values: " + unique);

        List<Number> immutable = List.of(0);
        try {
            appendAll(integers, immutable);
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "Immutable destination: "
                    + "UnsupportedOperationException");
        }

        List<? extends Number> producer = integers;
        System.out.println(
                "Producer read: " + producer.get(0));

        List<? super Integer> consumer =
                new ArrayList<Number>();
        consumer.add(9);
        System.out.println("Consumer read type: "
                + consumer.get(0).getClass().getSimpleName());

        List<Number> standard =
                new ArrayList<>(List.of(-1, -1, -1));
        Collections.copy(standard, integers);
        System.out.println(
                "Collections.copy: " + standard);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 -Xlint:all PecsCopyDemo.java
java PecsCopyDemo
```

**Standard output** (không có dữ liệu tùy thời điểm):

```text
Append count: 3
Numbers: [0.5, 2, 4, 6]
Objects: [2, 4, 6]
Replaced count: 3
Slots: [2, 4, 6, -1]
Too small: IndexOutOfBoundsException
Too small unchanged: [-1, -1]
Self-copy count: 3
Self-copy: [1, 2, 3, 1, 2, 3]
Overlapping views: [1, 1, 2, 3]
Mapped count: 3
Mapped: [1.0, 2.0, 3.0]
Set processed: 3
Set values: [2, 4, 6]
Immutable destination: UnsupportedOperationException
Producer read: 2
Consumer read type: Integer
Collections.copy: [2, 4, 6]
```

Điểm đáng chú ý:

- Dòng đầu dùng `List<Integer>` và `List<Number>`: compiler chấp nhận nhờ PECS.
- `List<Object>` cũng là destination hợp lệ.
- `overwritePrefix` **thay các vị trí đầu** và giữ `-1` cuối; không append.
- Destination thiếu vị trí bị từ chối **trước vòng ghi**, nên trong ví dụ nó vẫn giữ `[-1,-1]`.
- Self-append dùng snapshot nên thành `[1,2,3,1,2,3]`, không duyệt một collection đang bị chính vòng lặp `add` làm biến đổi.
- Hai views chồng lấn cho kết quả `[1,1,2,3]` vì copy vào snapshot trước.
- `Set` minh họa **đếm lần xử lý** khác **đếm giá trị mới được thêm**.
- `List.of` có signature phù hợp nhưng không hỗ trợ sửa đổi, nên lỗi thuộc hợp đồng runtime của collection.
- `Collections.copy` thể hiện cách sao chép có sẵn trong JDK với vùng đích đủ lớn.

## 14. Lựa chọn hợp đồng null

Một chữ ký `<T> void copy(...)` **không có nghĩa `T` luôn non-null**. Khi nguồn chứa `null`, việc destination có chấp nhận không phụ thuộc API cụ thể:

```java
List<String> source = new ArrayList<>();
source.add(null);

List<Object> allowNull = new ArrayList<>();
appendAll(source, allowNull); // Có thể chấp nhận null.

List<Object> noNull = new ArrayList<>(List.of("existing"));
// Không suy ra mọi implementation của List cho phép null.
```

Các collection từ factory `List.of` không cho phép null và không cho sửa, trong khi `ArrayList` cho phép null. `Set.of` cũng cấm null theo hợp đồng của nó.

Nếu API sao chép cần cấm null, kiểm tra rõ ràng:

```java
for (T value : source) {
    destination.add(Objects.requireNonNull(value, "element"));
}
```

Nếu cần **chặn hết dữ liệu xấu trước khi ghi bất cứ thứ gì**, phải xác minh/snapshot toàn bộ nguồn trước khi bắt đầu đụng tới đích. Nhưng điều đó không tự giải quyết exception từ `destination.add` hay mutation từ thread khác.

Nếu dữ liệu nghiệp vụ cho phép null, đừng dùng `List.copyOf(source)` như một bước snapshot mà quên rằng factory này từ chối null; `new ArrayList<>(source)` cho phép giữ null trong cấu trúc copy.

## 15. Mutation, partial failure và atomicity

PECS giải quyết **tương thích kiểu**, không phải tính chất giao dịch của hàm copy.

Những lỗi có thể xảy ra:

1. `destination.add` ném `UnsupportedOperationException` vì collection không hỗ trợ thêm.
2. `destination.set` ném exception vì list unmodifiable hoặc kiểm soát từng vị trí.
3. `destination.add` từ chối một phần tử do null/loại giá trị/hợp đồng đặc biệt.
4. Nguồn bị sửa trong lúc đang lặp, có thể gây `ConcurrentModificationException` hoặc dữ liệu không nhất quán tùy implementation.
5. Callback `mapper` ném exception khi xử lý một phần tử nào đó.
6. Các collection giới hạn dung lượng có thể từ chối thêm sau một số lần.
7. Caller cung cấp nguồn vô hạn/lazy iterable; việc snapshot toàn bộ sẽ không kết thúc.

Với `appendAll`, nếu phần tử thứ ba gây lỗi, phần tử thứ nhất và thứ hai **có thể đã được thêm**. `appendSnapshot` chỉ tách giai đoạn **đọc nguồn** khỏi **ghi đích**, không làm các lần `add` thành một transaction atomic.

Với `overwritePrefix`, kiểm tra đủ độ dài trước giúp loại bỏ lỗi **đích quá ngắn ở thời điểm kiểm tra**, nhưng các `set` vẫn có thể thất bại hoặc bị code khác quan sát trạng thái trung gian.

Nếu hệ thống yêu cầu **all-or-nothing**, cần cách tiếp cận khác: xây dựng một collection kết quả riêng rồi thay tham chiếu/commit theo ranh giới đồng bộ thích hợp, dùng transaction của persistence layer hoặc cơ chế ứng dụng cụ thể. Không hứa atomicity chỉ vì có một snapshot local.

## 16. Độ an toàn khi nhiều thread và dữ liệu mutable

Một input có thể là `Collection` mutable; nếu thread khác sửa nó trong khi đọc, kết quả có thể không nhất quán. `new ArrayList<>(source)` hay vòng `for` đưa phần tử vào snapshot **không phải** bảo đảm snapshot atomic cho mọi nguồn concurrent.

Các cách giải quyết tùy yêu cầu:

- Dùng cấu trúc immutable/snapshot đã tạo trước khi bắt đầu thao tác.
- Dùng `synchronized`/lock chung cho **cả người ghi lẫn người copy**, giữ lock đủ lâu để đọc một trạng thái nhất quán.
- Dùng collection đồng thời với semantics iteration được tài liệu hóa, chấp nhận kiểu consistent view của nó khi phù hợp.
- Nếu đích cũng có shared readers/writers, bảo đảm họ đồng bộ với phase ghi hoặc dùng copy-on-write/publish kết quả.

Tính an toàn generic type arguments không giải quyết race condition. Một method `<T>` hợp lệ vẫn có thể không thread-safe.

### Tham chiếu phần tử và deep copy

`appendSnapshot` và `overwritePrefix` chỉ **sao chép tham chiếu phần tử**, không clone các object mutable.

```java
List<StringBuilder> source =
        List.of(new StringBuilder("A"));
List<Object> target = new ArrayList<>();

appendSnapshot(source, target);
source.get(0).append("B");

System.out.println(target.get(0)); // AB
```

Đó là **shallow copy**. Nếu cần giá trị độc lập sâu, phải có mapper/copier do domain cung cấp và xử lý trạng thái mutable bên trong từng phần tử, không thể trông chờ wildcard `? extends T` làm việc ấy.

## 17. Đặt tên tham số và viết Javadoc phù hợp PECS

Nếu là public API, nên mô tả vai trò **source/destination** và ý nghĩa return:

```java
/**
 * Appends every visited source element to destination.
 *
 * <p>The destination must support add operations. This method
 * may partially modify destination before an exception occurs.
 *
 * @param <T> element type transferred from source to destination
 * @param source producer of elements compatible with T
 * @param destination consumer accepting elements of type T
 * @return number of source elements whose destination.add call completed
 * @throws NullPointerException if source or destination is null
 * @throws UnsupportedOperationException if destination rejects an add
 */
static <T> int appendAll(
        Iterable<? extends T> source,
        Collection<? super T> destination) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(destination, "destination");
    int count = 0;
    for (T value : source) {
        destination.add(value);
        count++;
    }
    return count;
}
```

**Phân biệt `@param <T>` với `@param source`:** tag đầu mô tả type parameter; tag sau mô tả formal value parameter. Khi đổi từ processed-count sang accepted-count, phải sửa cả tên và Javadoc; nếu không API có bug về **semantics được hứa**, dù type checking vẫn đúng.

Một design để tránh nhầm thứ tự hai đối số có thể đặt destination trước như `Collections.copy(dest,src)`; một design khác đặt source trước như `appendAll(source,destination)`. Cả hai được nếu tài liệu và tên biến rõ. **Đừng chỉ nhìn hai wildcard mà đoán thứ tự tham số** khi tên method không rõ ràng.

## 18. Kiểm thử đúng compile-time và runtime

Các **positive compile tests** cần có:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

appendAll(integers, numbers);
appendAll(integers, objects);
```

Một **negative compile test** (đặt trong file riêng cố ý không compile):

```java
List<Number> source = List.of(1, 2.5);
List<Integer> destination = new ArrayList<>();

// KHÔNG BIÊN DỊCH:
appendAll(source, destination);
```

Các **runtime tests** cần kiểm tra:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Nguồn rỗng, đích mutable | Đếm 0; không đổi đích |
| `List<Integer>` → `List<Number>` | Thành công, đúng thứ tự với list |
| `List<Integer>` → `List<Object>` | Thành công |
| `Set` đã có phần tử trùng | Processed-count gồm cả lời gọi `add` trả false |
| List đích unmodifiable | `UnsupportedOperationException` khi copy cố sửa |
| Overwrite với đích đủ vị trí | `size` đích giữ nguyên, các vị trí đầu đổi |
| Overwrite với đích quá ngắn | Exception, được kiểm tra trước vòng `set` |
| Self-append với snapshot | Nối đúng bản chụp của nguồn |
| Hai `subList` chồng lấn | Kết quả dựa trên snapshot nguồn ban đầu |
| Nguồn có null | Theo chính sách null của method và destination |
| Mapper chuyển `Integer` → `Double` | Kết quả tương thích `Collection<Number>` |
| Mapper ném exception | Không hứa rollback các phần tử đã thêm |
| Concurrent mutation | Không mặc định bảo đảm snapshot nhất quán |

Trong JUnit, dùng các phép kiểm tra như `assertEquals`/ `assertThrows` để test **giá trị và exception thực**. Một bài test chỉ nhìn lời gọi compile thành công không chứng minh destination hỗ trợ mutation; ngược lại, một runtime test không thay thế được negative compilation test về type safety.

## 19. Những lỗi thường gặp

**Lỗi 1 — Viết hai `List<T>` vì “đều chứa T”.** Nếu mục đích chỉ đọc nguồn và ghi đích, `? extends T`/`? super T` cho phép subtype/supertype mà invariant `List<T>` không diễn tả được.

**Lỗi 2 — Đảo ngược PECS.** `Collection<? extends T>` không phải kiểu phù hợp để thêm `T` non-null tùy ý; `Iterable<? super T>` không bảo đảm đọc ra `T`.

**Lỗi 3 — Ép `List<Integer>` sang `List<Number>`.** Unchecked cast không biến collection thành kiểu an toàn rộng hơn; dữ liệu `Double` có thể phá hợp đồng `Integer`.

**Lỗi 4 — Tưởng `Collections.copy` tự tăng size của destination.** Nó ghi đè, yêu cầu số vị trí đang có đủ cho source.

**Lỗi 5 — Dùng `new ArrayList<>(n)` và tưởng list có n phần tử.** Constructor này chỉ đặt initial capacity, không đặt size.

**Lỗi 6 — Dùng `addAll` khi muốn ghi đè.** `addAll` thêm phần tử, không thay các vị trí đầu bằng `set`.

**Lỗi 7 — Tưởng typed destination luôn mutable.** `List.of`, unmodifiable views và các implementation khác có thể từ chối `add`/`set` ở runtime.

**Lỗi 8 — Đếm `processed` như số phần tử mới của `Set`.** `add` trả `false` có thể được tính là một lần xử lý thành công nhưng không làm size tăng.

**Lỗi 9 — Copy trực tiếp giữa các views chồng lấn mà không xét alias.** Cần snapshot hoặc thuật toán có thứ tự đọc–ghi được chứng minh an toàn.

**Lỗi 10 — Cho nguồn và đích là một collection khi vòng for-each vừa đọc vừa thêm.** Có thể lỗi concurrent modification hoặc semantics không mong muốn; snapshot trước nếu muốn hỗ trợ tình huống đó.

**Lỗi 11 — Tưởng snapshot tạo deep copy.** Nó chỉ giữ các references, không clone object phần tử.

**Lỗi 12 — Tưởng snapshot tự tạo atomic transaction.** Exception khi ghi đích vẫn có thể làm đích thay đổi một phần; concurrent writes cũng cần đồng bộ riêng.

**Lỗi 13 — Tưởng generic `T` luôn non-null.** Chính sách null nằm ở method và collection, không được type parameter tự bảo đảm.

**Lỗi 14 — Dùng raw types để cho phép các loại collection khác nhau.** API wildcard typed đã diễn đạt đúng nhu cầu mà không bỏ compiler checks.

**Lỗi 15 — Quên `? super S`/`? extends R` khi viết mapper.** Callback cần nhận source và sản xuất result; PECS áp dụng cả ở type arguments của `Function`.

## 20. Bài tập tự luyện

**Bài 1.** Viết `<T> int appendAll(Iterable<? extends T>, Collection<? super T>)`. Nêu chính xác ý nghĩa `int` nếu đích là `Set`.

**Gợi ý:** đếm sau khi `add` hoàn tất là “số phần tử đã xử lý”, không phải số phần tử mới nếu `add` trả `false`.

**Bài 2.** Cho `List<Integer> source` và `List<Number> target`, hãy gọi method mà không cast; thử `List<Object>` làm target. Giải thích vì sao cùng hợp lệ.

**Đáp án cốt lõi:** target là consumer của những phần tử nguồn; `Number` và `Object` đều nhận được `Integer`.

**Bài 3.** Cho `List<Number> source` chứa `Integer` và `Double`, và `List<Integer> target`. Vì sao không thể copy toàn bộ giữ nguyên kiểu?

**Đáp án:** target không nhận mọi `Number`. Nếu nghiệp vụ yêu cầu chuyển `Double` thành `Integer`, phải viết mapper/validator có chính sách rõ, không dùng unchecked cast.

**Bài 4.** `Collections.copy(new ArrayList<>(10), List.of(1,2))` có chạy thành công không?

**Đáp án:** không, nếu destination lúc gọi vẫn có size 0; capacity 10 không đồng nghĩa có 10 vị trí.

**Bài 5.** `Arrays.asList(0,0)` và `List.of(0,0)` khác nhau ra sao khi dùng làm đích của overwrite?

**Đáp án:** `Arrays.asList` hỗ trợ `set` nhưng không thay đổi kích thước; `List.of` không hỗ trợ mutation, kể cả `set`.

**Bài 6.** Khi source và destination là hai `subList` của cùng một list, vì sao `overwritePrefix` sao chép nguồn trước?

**Đáp án:** tránh các lệnh ghi vào destination thay đổi phần tử trong source mà vòng lặp còn chưa đọc.

**Bài 7.** Nếu `appendSnapshot(source, dest)` gặp lỗi trong `dest.add` ở phần tử cuối, có rollback các phần tử trước không?

**Đáp án:** không. Snapshot chỉ tách đọc nguồn khỏi ghi đích, không biến thao tác thành transaction.

**Bài 8.** `Collection<? super Integer>` đọc ra kiểu gì an toàn nếu không có thông tin thêm?

**Đáp án:** `Object`. Compiler không biết tham chiếu hiện giữ `Collection<Integer>`, `Collection<Number>` hay `Collection<Object>`.

**Bài 9.** Thiết kế helper chuyển giá trị `String` thành `Integer` rồi append vào `Collection<Number>`.

**Gợi ý:** dùng `mapAppend(strings, numbers, Integer::parseInt)`, với `Function<? super S,? extends R>`; cân nhắc `NumberFormatException` và partial writes.

**Bài 10.** Bổ sung một biến thể `tryAppendAll` báo số lần `Collection.add` trả `true`, phân biệt với số lần đã duyệt. Viết test với `LinkedHashSet` có trùng key.

## 21. Checklist trước khi công bố API sao chép

1. **Ý định là append hay overwrite?** Tên method, logic và Javadoc phải thống nhất.
2. **PECS đặt đúng chiều chưa?** Nguồn `? extends T`, đích `? super T`.
3. **Đã chọn abstraction tối thiểu?** Chỉ cần iterator thì `Iterable`; cần `set(i)` thì `List`.
4. **Có thực sự cần một `<T>` được đặt tên không?** Khi phải nối quan hệ nguồn–đích, có.
5. **Có tránh raw casts không?** Nếu cần conversion, dùng mapper rõ ngữ nghĩa.
6. **Đích cần sẵn size hay tự tăng size?** Đây là điểm khác biệt chính giữa `Collections.copy` và append.
7. **Return value đếm gì?** Processed, accepted, inserted, hay old values?
8. **Có kiểm tra null source/dest/mapper?** Chính sách null element nằm ở đâu?
9. **Có hỗ trợ self-copy/overlap không?** Nếu có, snapshot/thuật toán đã được chứng minh chưa?
10. **Có hứa atomicity không?** Nếu không, nêu khả năng partial mutation khi lỗi.
11. **Destination có thể không hỗ trợ modification?** Có nêu `UnsupportedOperationException` theo hợp đồng?
12. **Với `Set`, có phân biệt số phần tử xử lý và size tăng không?**
13. **Có concurrency policy không?** Snapshot O(n) không tự bảo đảm thread safety.
14. **Có kiểm tra nested mutable values không?** Shallow copy không clone trạng thái object.
15. **Có test compile-time sai chiều type không?** Ví dụ `List<Number>` → `List<Integer>` phải bị từ chối.
16. **Có test runtime size, alias, null, unsupported operations và mapper exceptions không?**
17. **Tài liệu có nêu rõ yêu cầu về order, duplicates và hiệu năng theo implementation không?**

## 22. Kết luận

**PECS là cách biểu diễn chiều dịch chuyển dữ liệu ở cấp kiểu.** Khi viết hàm sao chép từ nguồn sang đích, hãy bắt đầu bằng **`Iterable<? extends T>` cho nơi đọc** và **`Collection<? super T>` cho nơi ghi**, hoặc với thao tác theo vị trí, dùng **`List<? extends T>` và `List<? super T>`**. Các wildcard giúp Java cho phép truyền phần tử kiểu con sang container kiểu cha mà vẫn được compiler kiểm tra.

Nhưng một hàm `copy` tốt còn phải nói rõ **nó append hay overwrite**, có **yêu cầu đủ chỗ**, có **xử lý overlapping views**, đếm **số phần tử đã duyệt hay thật sự thêm**, và có các **hợp đồng null, mutation, error, alias, concurrency** ra sao. `Collections.copy` là một ví dụ PECS chuẩn cho việc ghi đè; `appendAll`, `appendSnapshot`, `overwritePrefix` và `mapAppend` minh họa cách thiết kế các biến thể đúng semantics mà không cần raw types hay unchecked casts.

Hãy để **chữ ký thể hiện tính an toàn kiểu**, **tên method thể hiện thao tác**, và **Javadoc/tests chứng minh các hành vi runtime**.