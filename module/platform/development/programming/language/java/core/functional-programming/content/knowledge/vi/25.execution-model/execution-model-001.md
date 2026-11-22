# Pipeline được xây dựng trước và thực thi khi có thao tác kết thúc trong Java Stream

Trong Java Stream API, một chuỗi lời gọi **filter**, **map**, **sorted** hay **distinct** thường chỉ **xây dựng một pipeline mô tả cách xử lý dữ liệu**, chứ chưa xử lý ngay từng phần tử. Việc đánh giá pipeline thường diễn ra khi có **terminal operation** như **toList**, **collect**, **count**, **reduce**, **forEach** hoặc **findFirst**.

Đặc tính này gọi là **lazy evaluation** — đánh giá theo nhu cầu. Nó giúp Stream kết hợp nhiều bước xử lý mà không phải tạo các collection trung gian sau mỗi bước. Nhưng nếu hiểu nhầm rằng lời gọi map/filter lập tức chạy callback, chương trình có thể ghi log thiếu, bắt ngoại lệ sai vị trí hoặc tưởng Stream đã cập nhật dữ liệu trước khi một kết quả được yêu cầu.

Bài học thuộc phần **Cơ chế thực thi**, tập trung vào trình tự **nguồn dữ liệu → xây dựng pipeline → thao tác kết thúc → thực thi**, sự khác nhau giữa intermediate/terminal operations, cách xử lý từng phần tử, short-circuit, tối ưu hóa, tài nguyên, ngoại lệ, Stream một lần dùng và các ví dụ Java 17+ chạy được.

## 1. Hình dung ngắn gọn: xây dựng trước, tiêu thụ sau

Ví dụ:

~~~java
List<String> names = List.of("An", "Binh", "Mai");

Stream<String> pipeline = names.stream()
    .filter(name -> name.length() > 2)
    .map(String::toUpperCase);

// Đến đây chưa yêu cầu lấy ra các phần tử kết quả.

List<String> result = pipeline.toList();
System.out.println(result); // [BINH, MAI]
~~~

Hai lời gọi **filter** và **map** là intermediate operations. Chúng tạo các bước của pipeline; lệnh **toList()** là terminal operation yêu cầu kết quả List và khiến Stream đánh giá những phần tử cần thiết.

Có thể hình dung:

~~~text
GIAI ĐOẠN 1 — XÂY DỰNG
List<String> names
       │
       └── stream() ── filter(...) ── map(...)
                                      │
                                      └── pipeline được khai báo

GIAI ĐOẠN 2 — ĐÁNH GIÁ
pipeline ── toList()
               │
               ├── lấy phần tử từ nguồn khi cần
               ├── áp dụng điều kiện filter
               ├── áp dụng phép biến đổi map
               └── thu phần tử đầu ra vào List
~~~

Sơ đồ thể hiện ý nghĩa **logic**, không mô tả cam kết về số lần callback hay các bước nội bộ cố định của mọi JVM. Các optimizer có thể bỏ qua những bước không ảnh hưởng đến kết quả hoặc chọn chiến lược khác.

**Mệnh đề cần ghi nhớ:** Có một Stream object và có một pipeline không đồng nghĩa dữ liệu nguồn đã được duyệt hoặc callback đã chạy.

## 2. Ba thành phần của một Stream pipeline

Một pipeline thông thường có:

1. **Nguồn (source):** Collection, array, generator, range, I/O hoặc nguồn khác.
2. **Các thao tác trung gian (intermediate operations):** filter, map, flatMap, sorted, distinct, limit, skip, peek, takeWhile… Mỗi lời gọi tạo một bước Stream.
3. **Một thao tác kết thúc (terminal operation):** toList, collect, count, reduce, sum trên primitive stream, forEach, findFirst, anyMatch… Phần này yêu cầu hoàn tất kết quả hoặc tạo một hiệu ứng theo hợp đồng.

| Thành phần | Ví dụ | Vai trò | Có trực tiếp trả Stream tiếp? |
| --- | --- | --- | --- |
| Source | names.stream(), Stream.of(...) | Cung cấp phần tử | Tạo Stream ban đầu |
| Intermediate | filter(predicate) | Giữ phần tử phù hợp | Có |
| Intermediate | map(function) | Biến phần tử T thành R | Có |
| Intermediate | distinct(), sorted() | Loại trùng hoặc sắp thứ tự | Có |
| Intermediate | limit(n), skip(n) | Giới hạn/bỏ qua phần tử | Có |
| Terminal | toList(), collect(...) | Thu kết quả | Không |
| Terminal | count(), reduce(...) | Tổng hợp dữ liệu | Không |
| Terminal | findFirst(), anyMatch(...) | Tìm/kiểm tra, có thể dừng sớm | Không |
| Terminal | forEach(action) | Tiêu thụ các phần tử với action | Không |

**Chú ý về tính lazy:** Đa số intermediate operations trên Java Stream đều lazy. Tuy nhiên, một số phép như sorted và distinct **có trạng thái (stateful)** và có thể cần buffering khi terminal operation chạy. “Lazy” không đồng nghĩa không tốn bộ nhớ hoặc tất cả phần tử luôn được xử lý hoàn toàn độc lập.

### 2.1. Stream có kiểu dữ liệu, không phải một List khác

~~~java
Stream<String> stream = names.stream()
    .filter(name -> name.length() > 2);
~~~

stream không phải một List<String> mới đã chứa các tên lọc xong. Nó là **một đối tượng biểu diễn pipeline** có thể được tiêu thụ để nhận kết quả. Khi cần truy cập nhiều lần, hãy giữ nguồn thích hợp hoặc thu kết quả thành List rồi tạo Stream mới từ đó.

### 2.2. Terminal operation không nhất thiết trả Collection

~~~java
long count = names.stream().filter(s -> s.length() > 2).count();

boolean anyLong = names.stream()
    .anyMatch(s -> s.length() > 4);

Optional<String> first = names.stream()
    .filter(s -> s.length() > 2)
    .findFirst();
~~~

**count** trả long; **anyMatch** trả boolean; **findFirst** trả Optional<String>. Chỉ một số terminal operation tạo List/Map/Set hoặc collection qua collector. Kiểu dữ liệu đầu ra phụ thuộc **terminal operation**, không phụ thuộc việc nguồn là List.

## 3. Kiểm chứng tính lazy bằng bộ đếm trong ví dụ có kiểm soát

Xét:

~~~java
List<String> source = List.of("An", "Binh", "Mai", "Duyen");
AtomicInteger visits = new AtomicInteger();

Stream<String> pipeline = source.stream()
    .filter(name -> {
        visits.incrementAndGet();
        return name.length() > 2;
    })
    .map(String::toUpperCase);

System.out.println("after-build=" + visits.get());

List<String> result = pipeline.toList();

System.out.println("result=" + result);
System.out.println("after-terminal=" + visits.get());
~~~

Đây là đoạn minh họa nằm trong phương thức với import List, Stream và AtomicInteger. Với nguồn và terminal **toList** trong ví dụ Java 17 đã kiểm thử, kết quả:

~~~text
after-build=0
result=[BINH, MAI, DUYEN]
after-terminal=4
~~~

**Giải thích:** Trước khi gọi toList(), bộ đếm visits vẫn bằng 0. Khi toList() đòi phần tử kết quả, bốn chuỗi nguồn được kiểm tra điều kiện filter; ba chuỗi có độ dài trên 2 tiếp tục được map thành chữ hoa.

Đây là **thí nghiệm quan sát** để học thời điểm chạy callback, không phải khuôn mẫu thực hành nhằm đưa side effect vào filter. Trong code nghiệp vụ, callback Stream nên càng **stateless** và **non-interfering** càng tốt. Một số terminal và đặc tính nguồn cho phép tối ưu để bỏ qua callback không cần thiết, nên không thể dùng bộ đếm trong map/filter như cơ chế audit bảo đảm số lần xử lý.

### 3.1. Vì sao có thể dựng pipeline mà chưa in gì?

~~~java
Stream<String> pipeline = names.stream()
    .map(name -> {
        System.out.println("mapping " + name);
        return name.toUpperCase();
    });

System.out.println("constructed");
~~~

Với các thao tác trên, chưa có terminal operation nên callback map **không được yêu cầu chạy**. Nếu có lệnh pipeline.toList() sau đó, việc tạo kết quả có thể khiến callback map được đánh giá. Tuy nhiên không nên dùng số lần println từ map để định nghĩa yêu cầu nghiệp vụ, vì Stream API cho phép tối ưu hóa và loại bỏ các bước không ảnh hưởng đến kết quả.

## 4. Pipeline được ghép theo từng phần tử, không nhất thiết theo từng danh sách trung gian

Người mới học đôi khi tưởng pipeline luôn làm như sau:

~~~text
Bước 1: lọc toàn bộ nguồn ra List A
Bước 2: map toàn bộ List A ra List B
Bước 3: trả List B
~~~

Đó **không phải yêu cầu tổng quát** của Java Stream. Với pipeline stateless như filter rồi map, runtime có thể thực hiện theo luồng dữ liệu kiểu **vertical processing**:

~~~text
Phần tử "An"   → filter false → bỏ
Phần tử "Binh" → filter true  → map "BINH" → gửi xuống terminal
Phần tử "Mai"  → filter true  → map "MAI"  → gửi xuống terminal
Phần tử "Duyen"→ filter true  → map "DUYEN"→ gửi xuống terminal
~~~

Phương pháp này tránh phải tạo một List A sau filter và một List B sau map. Đó là một trong những lợi ích của pipeline.

**Không suy diễn thứ tự callback tuyệt đối** từ sơ đồ. Thứ tự thực thi còn tùy nguồn, các stateful operations, short-circuit, chế độ parallel và các tối ưu hợp lệ. Hợp đồng kết quả quan trọng hơn việc callback được gọi vào chính xác thời điểm nào.

### 4.1. Stateless operations

Các bước như filter và map thường là **stateless intermediate operations** nếu callback không dùng trạng thái mutable phụ thuộc các phần tử khác.

~~~java
List<Integer> squares = List.of(1, 2, 3, 4).stream()
    .filter(number -> number % 2 == 0)
    .map(number -> number * number)
    .toList();
~~~

Kết quả là [4, 16]. Không cần tạo một List tạm chỉ chứa 2,4 trước khi bình phương.

### 4.2. Stateful operations

**sorted()** cần xét thứ tự của các phần tử, nên thường phải thu đủ dữ liệu liên quan trước khi có thể xuất kết quả sắp đúng. **distinct()** cần ghi nhớ phần tử đã thấy, tùy source và chiến lược.

~~~java
List<String> result = Stream.of("pear", "apple", "pear", "fig")
    .distinct()
    .sorted()
    .toList();
~~~

Kết quả [apple, fig, pear].

“Pipeline lazy” không đồng nghĩa mọi intermediate operation đều xử lý phần tử tức thì rồi bỏ đi. Với sorted trên dữ liệu lớn, việc giữ nhiều phần tử trong bộ nhớ có thể đáng kể.

### 4.3. Chỉ tạo pipeline không có nghĩa đã phát hiện lỗi dữ liệu

Nếu callback chứa logic có thể ném ngoại lệ:

~~~java
Stream<Integer> parsed = Stream.of("10", "wrong")
    .map(Integer::parseInt);
~~~

Khai báo parsed không tự biến toàn bộ dữ liệu thành Integer ngay. Khi một terminal operation thực sự đòi phần tử "wrong", Integer.parseInt có thể ném NumberFormatException.

Tuy nhiên **không phải mọi ngoại lệ đều bị trì hoãn**: lỗi ngay trong quá trình kiểm tra đối số hoặc tạo source, ví dụ gọi phương thức trên biến source null, có thể xảy ra lúc xây dựng. Chỉ nói đúng rằng **việc thực thi logic trên từng phần tử của intermediate operations thường bị hoãn**.

## 5. Short-circuit: terminal không cần duyệt hết nguồn

Một số terminal operations có thể trả kết quả sớm, như **findFirst, findAny, anyMatch, allMatch, noneMatch**. Điều này khiến bộ lọc hoặc mapper phía trước có thể chỉ chạy trên một phần nguồn.

Ví dụ với ordered List và sequential stream:

~~~java
List<String> source = List.of("An", "Binh", "Mai", "Duyen");
AtomicInteger tested = new AtomicInteger();

Optional<String> first = source.stream()
    .filter(name -> {
        tested.incrementAndGet();
        return name.length() >= 4;
    })
    .findFirst();

System.out.println(first.orElse("none")); // Binh
System.out.println(tested.get());         // 2
~~~

Với nguồn trên và pipeline tuần tự, phần tử đầu "An" không đạt điều kiện, phần thứ hai "Binh" đạt điều kiện. findFirst không cần yêu cầu các phần tử tiếp theo, nên số lần kiểm tra trong ví dụ là 2.

**Đừng lấy 2 làm số lần gọi bất biến cho mọi cấu trúc stream.** Nếu chuyển sang parallel stream, thêm sorted, thay nguồn hoặc đổi terminal operation, chiến lược đánh giá có thể khác.

### 5.1. anyMatch và allMatch

~~~java
boolean found = Stream.of("Go", "Java", "Rust")
    .anyMatch(name -> name.length() == 4); // true
~~~

Ở sequential stream thông thường, anyMatch có thể dừng khi gặp "Java". Tương tự:

- allMatch có thể dừng khi một phần tử không đạt điều kiện.
- noneMatch có thể dừng khi một phần tử đạt điều kiện.
- findAny có thể chọn bất kỳ phần tử phù hợp mà không hứa giữ encounter order như findFirst trên ordered stream.

Các phép này có **cơ hội short-circuit**, nhưng không nên dùng việc short-circuit làm cách bảo đảm một side effect ở callback sẽ chạy đúng một lần.

### 5.2. limit và takeWhile

~~~java
List<Integer> firstThree = IntStream.rangeClosed(1, 100)
    .limit(3)
    .boxed()
    .toList();
~~~

Kết quả [1, 2, 3]. Một pipeline có limit có thể không yêu cầu phần tử vượt giới hạn khi có đủ dữ liệu và điều kiện thích hợp.

Java 9+ có **takeWhile** và **dropWhile**. Với ordered stream, takeWhile giữ đoạn đầu liên tiếp còn thỏa predicate; nó không giống filter lấy mọi phần tử thỏa ở bất kỳ vị trí nào.

~~~java
List<Integer> prefix = Stream.of(1, 2, 3, 1, 2)
    .takeWhile(x -> x < 3)
    .toList();
~~~

Kết quả [1,2], không phải [1,2,1,2]. Bước intermediate như takeWhile vẫn là mô tả pipeline cho đến khi terminal operation đánh giá nó.

## 6. Terminal operation có thể tối ưu và bỏ qua callback

Một ngộ nhận thường gặp: “Đã gọi count() thì filter, map hay peek trước đó chắc chắn đều chạy qua từng phần tử”. Điều này **không luôn đúng**.

Với một nguồn có kích thước được biết và một pipeline không làm thay đổi số phần tử, Stream có thể xác định count mà **không cần duyệt từng phần tử**. Ví dụ:

~~~java
long total = List.of("A", "BB", "CCC").stream()
    .map(String::toUpperCase)
    .count();
~~~

Kết quả là 3. Với một nguồn List có size đã biết, việc count có thể được tối ưu mà không gọi map trên từng phần tử. Vì vậy:

~~~java
// Đừng kỳ vọng callback map này luôn thực thi:
long total = names.stream()
    .map(name -> {
        recordAudit(name); // side effect giả định
        return name.toUpperCase();
    })
    .count();
~~~

Đoạn trên chỉ minh họa lỗi thiết kế, **recordAudit** không phải Java API chuẩn hay phương thức được định nghĩa trong chương trình chạy mẫu.

**Quy tắc:** Stream được phép bỏ qua một bước nếu nó chứng minh bước đó không ảnh hưởng đến kết quả terminal theo hợp đồng. Side effect trong các intermediate operations không phải cơ chế đáng tin để ghi audit hoặc thay đổi trạng thái quan trọng.

### 6.1. peek chỉ dành cho quan sát/debug có điều kiện

~~~java
Stream<String> pipeline = names.stream()
    .peek(System.out::println);
~~~

peek là **intermediate operation**, không phải terminal. Nó không tự in dữ liệu chỉ vì pipeline được xây dựng. Ngay cả khi có terminal, một số thao tác được tối ưu hoặc short-circuit có thể khiến các lời gọi peek không diễn ra như bạn mong đợi.

Dùng peek để chẩn đoán pipeline một cách có ý thức; đừng dùng peek để cập nhật database, gửi thông báo, tính số tiền hay duy trì trạng thái nghiệp vụ quan trọng.

### 6.2. forEach là terminal, nhưng thứ tự cần chú ý

~~~java
names.stream().forEach(System.out::println);
~~~

forEach là terminal, nên yêu cầu tiêu thụ các phần tử phù hợp. Với parallel stream, **forEach không bảo đảm encounter order** của các action. Nếu việc hiển thị nhất thiết theo thứ tự nguồn, dùng **forEachOrdered** với một ordered stream, đồng thời chấp nhận đặc tính hiệu năng tương ứng.

Không nên dựa vào thứ tự in của peek/map trong parallel stream để suy ra thứ tự dữ liệu thu được.

## 7. Lỗi từ callback thường xuất hiện trong lúc terminal chạy

Xem:

~~~java
Stream<String> pipeline = Stream.of("ok", "bad", "later")
    .map(value -> {
        if (value.equals("bad")) {
            throw new IllegalArgumentException("bad element");
        }
        return value.toUpperCase();
    });

System.out.println("pipeline built");

try {
    pipeline.toList();
} catch (IllegalArgumentException error) {
    System.out.println(error.getMessage());
}
~~~

Với ví dụ này, việc xây dựng pipeline và in "pipeline built" xảy ra trước. Khi toList cố thu kết quả, lambda map gặp "bad" và ném IllegalArgumentException.

Điều quan trọng:

1. **Xây dựng pipeline** không tự gọi map trên từng phần tử.
2. **Terminal operation** kích hoạt việc xử lý cần thiết.
3. Ngoại lệ từ lambda có thể lan qua lời gọi terminal.
4. Sau một phép xử lý terminal thất bại, không nên tái sử dụng Stream đã bị tiêu thụ; hãy tạo Stream mới nếu cần retry với nguồn phù hợp.

Trong một chuỗi callback nhận dữ liệu I/O, ngoại lệ có thể xuất hiện khi nguồn được duyệt hoặc phần tử được ánh xạ, không nhất thiết lúc gọi API tạo source. Tuy nhiên, một số nguồn I/O cũng có thể ném IOException **ngay khi mở**; cần phân biệt hai giai đoạn.

## 8. Stream chỉ dùng một lần dù pipeline đã xây dựng

Một Stream pipeline có vòng đời sử dụng duy nhất.

~~~java
Stream<String> pipeline = names.stream()
    .filter(s -> !s.isBlank());

List<String> result = pipeline.toList();

// Sai: cùng Stream đã được sử dụng.
long count = pipeline.count();
~~~

Sau khi terminal operation hoàn tất, cùng instance Stream không thể tiếp tục xử lý một lượt mới. Một số tình huống reuse có thể gây **IllegalStateException**; hợp đồng API yêu cầu không tái sử dụng kể cả khi một implementation không phát hiện ra một kiểu reuse cụ thể.

Nếu cần kết quả từ cùng một **Collection** nhiều lần:

~~~java
List<String> result = names.stream()
    .filter(s -> !s.isBlank())
    .toList();

long count = names.stream()
    .filter(s -> !s.isBlank())
    .count();
~~~

Hai lời gọi names.stream() tạo hai pipeline mới từ nguồn Collection. **Không** phải cùng instance Stream được chạy lại.

### 8.1. Supplier<Stream<T>> khi cần pipeline mới

Có thể định nghĩa một factory:

~~~java
Supplier<Stream<String>> newStream =
    () -> names.stream().filter(s -> !s.isBlank());

List<String> result = newStream.get().toList();
long count = newStream.get().count();
~~~

Mỗi lần get() ở đây tạo Stream mới. Nếu factory trả lại một Stream đã cache, nó không giải quyết được quy tắc one-shot. Với nguồn I/O, tạo Stream mới có thể đồng nghĩa **mở lại nguồn** và phải quản lý tài nguyên cho từng lượt.

### 8.2. Đừng gọi một terminal operation rồi nối tiếp một intermediate operation

~~~java
// Không hợp lệ về kiểu nếu tiếp tục dùng Stream operator:
names.stream().count().filter(x -> true);
~~~

count trả long, không phải Stream. Về mặt API, terminal kết thúc chuỗi lời gọi pipeline; về mặt vòng đời, nó cũng tiêu thụ Stream tương ứng.

## 9. Pipeline với nguồn vô hạn hoặc dữ liệu lớn

Tính lazy có lợi khi nguồn sinh phần tử theo nhu cầu:

~~~java
List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
    .limit(5)
    .toList();
~~~

Kết quả [1,2,3,4,5]. Stream.iterate có thể tạo chuỗi không giới hạn; limit là bước trung gian giúp terminal toList dừng sau khi có đủ phần tử.

Ngược lại:

~~~java
// Không nên thực hiện với nguồn iterate vô hạn:
Stream.iterate(1, n -> n + 1).count();
~~~

count không thể hoàn thành bằng cách duyệt hết một nguồn vô hạn tổng quát. Việc dữ liệu được xử lý lazy không có nghĩa **mọi terminal operation đều sẽ kết thúc**.

### 9.1. Stateful operation có thể khiến pipeline phải tích lũy nhiều dữ liệu

Ví dụ:

~~~java
Stream<Integer> pipeline = Stream.iterate(1, n -> n + 1)
    .sorted();
~~~

Nếu terminal cần dữ liệu đã sắp xếp hoàn chỉnh từ nguồn vô hạn, pipeline có thể không có khả năng xuất kết quả theo cách hữu hạn. Ngay cả với nguồn hữu hạn lớn, sorted thường phải ghi nhớ nhiều phần tử để sắp xếp.

Cần hiểu **tính hữu hạn**, **short-circuit** và **thao tác có trạng thái** khi thiết kế xử lý dữ liệu lớn.

### 9.2. Không mọi pipeline giữ bộ nhớ O(1)

filter/map trên một nguồn tuần tự có thể thực thi kiểu truyền từng phần tử. Nhưng distinct, sorted, groupingBy, toList và những phép toán stateful khác có thể tích lũy dữ liệu. Lazy evaluation không bảo đảm không cấp phát bộ nhớ hoặc độ phức tạp hằng số.

## 10. Nguồn dữ liệu, late binding và non-interference

Một Stream có thể được lấy từ Collection:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Binh"));

Stream<String> pipeline = names.stream()
    .filter(s -> s.length() > 2);
~~~

Dù pipeline chưa có terminal, điều này **không cho phép sửa Collection nguồn tùy tiện** rồi mong kết quả luôn giống nhau. Hợp đồng Stream yêu cầu các callback không can thiệp nguồn và trạng thái nguồn không bị sửa trái phép trong quá trình pipeline được sử dụng.

Một số source Spliterator có cơ chế **late binding**, khiến việc liên kết phần tử với nguồn có thể bị trì hoãn đến giai đoạn đánh giá; nhưng đó không phải lý do để phụ thuộc vào mutation giữa lúc tạo Stream và terminal.

### 10.1. Cách làm an toàn khi cần snapshot

Nếu nguồn mutable và bạn cần kết quả trên một **snapshot cấu trúc dữ liệu**, hãy tạo bản chụp độc lập phù hợp trước:

~~~java
List<String> snapshot = List.copyOf(names);

List<String> result = snapshot.stream()
    .filter(s -> s.length() > 2)
    .toList();
~~~

List.copyOf tạo một List không thể chỉnh sửa ở mức cấu trúc, nhưng không tự deep-copy các phần tử mutable. Với String immutable, chia sẻ phần tử là hợp lý; với object mutable, cần cân nhắc snapshot sâu nếu dữ liệu có thể thay đổi từ bên ngoài.

### 10.2. Stateless callback và parallel stream

~~~java
List<String> result = names.parallelStream()
    .filter(s -> s.length() > 2)
    .map(String::toUpperCase)
    .toList();
~~~

Pipeline có thể xử lý các phần tử trên nhiều thread. Không viết filter/map phụ thuộc một biến đếm không đồng bộ hoặc sửa cùng List nguồn. Cơ chế parallel không thay đổi thời điểm khái niệm: intermediate pipeline được định nghĩa trước và terminal operation yêu cầu đánh giá; nhưng **thứ tự và cách chia việc** có thể khác.

## 11. Kết hợp Stream với I/O và AutoCloseable

Một số Stream không chỉ đọc dữ liệu trong bộ nhớ mà có thể giữ tài nguyên bên ngoài, chẳng hạn **Files.lines(Path)**.

~~~java
try (Stream<String> lines = Files.lines(path)) {
    List<String> matching = lines
        .filter(line -> line.startsWith("INFO"))
        .toList();
}
~~~

Đây là đoạn minh họa cần import Files, Path, Stream, List và xử lý IOException. **Files.lines** có thể mở tài nguyên ngay khi gọi để tạo Stream; pipeline filter được đánh giá theo nhu cầu terminal. Vì vậy cần phân biệt:

- **Tạo source I/O:** có thể mở tệp, cấp phát tài nguyên hoặc báo lỗi ngay.
- **Xây dựng intermediate pipeline:** thường chưa đọc/xử lý từng dòng bằng callback.
- **Chạy terminal:** có thể bắt đầu/tiếp tục đọc dòng và thực hiện filter/map.
- **Đóng Stream:** giải phóng tài nguyên gắn với nguồn, cần làm ngay cả khi terminal ném lỗi.

**Terminal operation không tự động thay thế close.** Dùng try-with-resources cho Stream có nguồn I/O như Files.lines, Files.walk, Files.list và Files.find. Với Stream thuần từ List trong bộ nhớ, thông thường không cần đóng vì không giữ tài nguyên ngoài.

### 11.1. Không có terminal thì vẫn phải đóng tài nguyên nguồn đã mở

~~~java
try (Stream<String> lines = Files.lines(path)) {
    Stream<String> selected = lines.filter(s -> !s.isBlank());
    // Không gọi terminal trong ví dụ này.
}
~~~

Ngay cả khi không yêu cầu xử lý dòng, Files.lines vẫn có thể giữ tài nguyên đã mở. try-with-resources bảo đảm đóng sau khi rời khối. Vì thế **lazy element processing không đồng nghĩa lazy resource acquisition**.

### 11.2. Ngoại lệ I/O có thể xuất hiện ở nhiều giai đoạn

- IOException có thể xuất hiện khi gọi Files.lines để mở nguồn.
- UncheckedIOException có thể xuất hiện khi duyệt các dòng của Stream, theo hợp đồng API.
- Lỗi trong callback map/filter có thể xuất hiện khi terminal cần phần tử.
- Lỗi close có thể xuất hiện khi rời try-with-resources.

Thiết kế code nên có ranh giới xử lý lỗi phù hợp với vòng đời tài nguyên, không chỉ bắt ngoại lệ ở một lời gọi intermediate.

## 12. Phân biệt lazy evaluation với deferred computation nói chung

Lazy evaluation trong Stream không có nghĩa mọi giá trị Java đều lazy. Một đối số truyền cho lời gọi phương thức Java thông thường vẫn được đánh giá theo quy tắc ngôn ngữ trước khi gọi phương thức, trừ những cấu trúc cụ thể của ngôn ngữ/API.

Ví dụ:

~~~java
List<String> names = loadNames();
Stream<String> pipeline = names.stream().map(String::trim);
~~~

Đoạn minh họa giả định có phương thức loadNames. **loadNames() chạy để tạo List trước khi có Stream**; Stream.map không làm cho lời gọi loadNames() trở thành lazy.

Tương tự:

~~~java
String prefix = calculatePrefix();
Stream<String> pipeline = names.stream()
    .map(name -> prefix + name);
~~~

calculatePrefix chạy khi gán prefix, trước terminal. Chỉ việc áp dụng **lambda map lên từng name** được hoãn theo cơ chế Stream.

Nếu muốn trì hoãn tạo dữ liệu, có thể thiết kế Supplier, generator, Stream.iterate/generate hoặc nguồn I/O tùy mục tiêu; không thể chỉ đặt lời gọi ở một biểu thức Java rồi mong nó tự trì hoãn.

### 12.1. Lambda là mô tả hành vi, gọi lambda mới thực thi thân

Khi viết:

~~~java
Function<String, String> upper = text -> text.toUpperCase();
~~~

đối tượng hàm được tạo nhưng thân text.toUpperCase không chạy ngay. Với Stream, callback do các thao tác pipeline giữ lại và được gọi trong quá trình đánh giá terminal khi cần. Đây là lý do **không nên nhầm định nghĩa lambda với gọi lambda**.

Ngoài Stream API, gọi upper.apply("java") thực thi lambda trực tiếp; không có khái niệm terminal operation của Stream ở đây.

## 13. Chương trình Java 17+ hoàn chỉnh

Chương trình sử dụng nguồn List, AtomicInteger để **quan sát thời điểm chạy callback**, các thao tác có trạng thái, short-circuit và một callback chủ ý ném lỗi. Mọi kết quả được in rõ ràng và đã được kiểm thử bằng **javac --release 17**.

Tạo tệp **StreamPipelineExecutionDemo.java**:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamPipelineExecutionDemo {
    public static void main(String[] args) {
        List<String> source = List.of("An", "Binh", "Mai", "Duyen");
        AtomicInteger visits = new AtomicInteger();

        Stream<String> pipeline = source.stream()
            .filter(name -> {
                visits.incrementAndGet();
                return name.length() > 2;
            })
            .map(String::toUpperCase);

        System.out.println("after-build=" + visits.get());
        System.out.println("result=" + pipeline.toList());
        System.out.println("after-terminal=" + visits.get());
        System.out.println("source=" + source);

        AtomicInteger tested = new AtomicInteger();
        Optional<String> first = source.stream()
            .filter(name -> {
                tested.incrementAndGet();
                return name.length() >= 4;
            })
            .findFirst();
        System.out.println("first=" + first.orElse("none"));
        System.out.println("tested=" + tested.get());

        System.out.println("sorted=" + Stream.of("pear", "apple", "pear", "fig")
            .distinct().sorted().toList());

        System.out.println("odd-sum=" + IntStream.rangeClosed(1, 5)
            .filter(number -> number % 2 == 1).sum());

        Stream<String> delayedError = Stream.of("ok", "bad", "later")
            .map(value -> {
                if (value.equals("bad")) {
                    throw new IllegalArgumentException("bad element");
                }
                return value.toUpperCase();
            });
        System.out.println("error-pipeline-built");
        try {
            delayedError.toList();
        } catch (IllegalArgumentException error) {
            System.out.println("terminal-error=" + error.getMessage());
        }

        try {
            pipeline.count();
        } catch (IllegalStateException error) {
            System.out.println("reuse=" + error.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp bằng **JDK 17 trở lên**:

~~~bash
javac StreamPipelineExecutionDemo.java
java StreamPipelineExecutionDemo
~~~

**Stdout chính xác:**

~~~text
after-build=0
result=[BINH, MAI, DUYEN]
after-terminal=4
source=[An, Binh, Mai, Duyen]
first=Binh
tested=2
sorted=[apple, fig, pear]
odd-sum=9
error-pipeline-built
terminal-error=bad element
reuse=IllegalStateException
~~~

### 13.1. Giải thích các kết quả

**after-build=0:** Việc gọi filter/map để tạo pipeline chưa yêu cầu đánh giá các phần tử List.

**result:** toList đòi các phần tử kết quả và hoàn tất việc lọc/map trong ví dụ; ba tên đạt điều kiện được biến thành chữ hoa.

**after-terminal=4:** Bốn tên được bộ lọc xem xét trong phép thu về List. Con số này thuộc **pipeline cụ thể đã kiểm thử**, không phải hợp đồng số lần callback chung.

**source:** List ban đầu vẫn là [An, Binh, Mai, Duyen], vì filter và map không sửa nguồn trong ví dụ.

**first=Binh và tested=2:** findFirst trên sequential stream có thứ tự nguồn đã dừng khi gặp tên đầu tiên có ít nhất bốn ký tự.

**sorted:** distinct loại bản sao "pear"; sorted sắp các giá trị còn lại theo natural order String.

**odd-sum=9:** IntStream.rangeClosed tạo các số 1 đến 5; lọc số lẻ rồi sum cho 1+3+5=9.

**error-pipeline-built:** callback map chưa được đánh giá tới phần tử "bad" khi pipeline được tạo.

**terminal-error=bad element:** khi toList thực thi pipeline, lambda gặp "bad" và ném IllegalArgumentException; lỗi được bắt ở ranh giới terminal.

**reuse=IllegalStateException:** sau toList, cố chạy count trên cùng instance Stream là sai; ví dụ minh họa hành vi từ JDK 17 đã chạy.

### 13.2. Vì sao ví dụ dùng AtomicInteger?

AtomicInteger giúp theo dõi số lần callback trong thí nghiệm quan sát mà không cần thao tác trên biến int local bị giới hạn bởi quy tắc effectively final. Nhưng **atomic không đồng nghĩa nghiệp vụ nên có side effect trong filter**. Không sao chép bộ đếm này thành một phần cần thiết của thuật toán song song; nếu chỉ cần đếm phần tử, hãy dùng count và hợp đồng của Stream.

## 14. Phân biệt các terminal operations khi đọc code

| Terminal | Kiểu kết quả thường gặp | Cần lưu ý |
| --- | --- | --- |
| toList() | List<T> | Java 16+ trả List không thể chỉnh sửa |
| collect(toList()) | List<T> | Collector không cam kết cụ thể implementation/mutability |
| count() | long | Có thể tối ưu, không luôn gọi mọi callback |
| reduce(...) | T, Optional<T> hoặc U | Cần quy tắc reduction phù hợp |
| findFirst() | Optional<T> | Short-circuit, chú ý encounter order |
| findAny() | Optional<T> | Không hứa chọn phần tử đầu theo thứ tự |
| anyMatch/allMatch/noneMatch | boolean | Có thể short-circuit |
| forEach(action) | void | Không cam kết thứ tự trên parallel stream |
| forEachOrdered(action) | void | Giữ encounter order khi nguồn có thứ tự |
| min/max(comparator) | Optional<T> | Chọn cực trị theo comparator |
| IntStream.sum() | int | Terminal trên primitive stream |

Một lỗi đọc code là tưởng **count** nhất thiết thực thi toàn bộ chuỗi logic map/peek như **toList**. Hãy nhớ các terminal cần **thông tin khác nhau**: count có thể chỉ cần kích thước, findFirst chỉ cần phần tử đầu, còn toList phải tạo danh sách kết quả.

**Tóm tắt:** Việc có terminal operation **kích hoạt đánh giá cần thiết để tạo kết quả**, không có nghĩa mọi callback trong pipeline chắc chắn được gọi, hoặc được gọi theo cùng số lần và thứ tự ở mọi JVM.

## 15. Các hiểu lầm và lỗi phổ biến

**Lỗi 1 — mong map/filter chạy ngay khi khai báo.** Intermediate operations thông thường chỉ tạo pipeline. Khi cần kết quả, gọi terminal operation phù hợp.

**Lỗi 2 — dựng pipeline mà không có terminal rồi tưởng logic đã thực thi.** Một Stream được tạo nhưng không tiêu thụ có thể không chạy lambda xử lý phần tử. Nếu thật sự muốn tạo dữ liệu, hãy thu vào List/collector hoặc dùng terminal theo hợp đồng.

**Lỗi 3 — dùng peek hoặc map làm nơi ghi audit bắt buộc.** Callback có thể không chạy do tối ưu, short-circuit hoặc thứ tự xử lý; hãy thực hiện side effect ở ranh giới được thiết kế rõ.

**Lỗi 4 — hiểu pipeline như danh sách các lượt duyệt toàn bộ.** Các thao tác stateless có thể được hợp nhất để xử lý theo từng phần tử, tránh collection trung gian.

**Lỗi 5 — nghĩ lazy nghĩa không tốn RAM.** sorted, distinct, collect, toList và các stateful operations vẫn có thể cần lưu nhiều dữ liệu.

**Lỗi 6 — coi findFirst giống count.** findFirst có thể dừng sớm; count thường cần tính số lượng nhưng cũng có thể được tối ưu dựa trên size đã biết.

**Lỗi 7 — quên Stream chỉ dùng một lần.** Sau terminal operation, không dùng lại Stream; tạo một Stream mới từ nguồn có thể duyệt lại.

**Lỗi 8 — nhầm lỗi tại lúc xây dựng với lỗi lúc terminal.** Lỗi kiểm tra tham số có thể xảy ra sớm; lỗi trong lambda xử lý phần tử thường xuất hiện khi pipeline được đánh giá.

**Lỗi 9 — thay đổi Collection nguồn trong khi pipeline hoạt động.** Vi phạm non-interference có thể gây lỗi hoặc kết quả không tin cậy, đặc biệt khi song song.

**Lỗi 10 — nghĩ parallel stream luôn xử lý cùng một thứ tự.** Không dùng callback làm nơi dựa vào thứ tự tuyệt đối hoặc cập nhật mutable state dùng chung.

**Lỗi 11 — quên close ở nguồn I/O.** Files.lines có thể mở tài nguyên ngay khi tạo Stream; dù pipeline không có terminal vẫn phải đóng khi không sử dụng.

**Lỗi 12 — tưởng Stream.iterate vô hạn nhưng count luôn sẽ trả.** Với nguồn vô hạn và không có giới hạn thích hợp, terminal có thể không kết thúc.

**Lỗi 13 — nghĩ Stream.toList giống Collectors.toList về mutability.** Stream.toList trả List không thể chỉnh sửa trong Java 17; Collectors.toList không hứa tính chất cụ thể.

**Lỗi 14 — dùng side effect để kiểm chứng hiệu năng.** Bộ đếm callback có thể bị optimizer bỏ qua nên không đo đúng tổng chi phí, nhất là với parallel stream. Dùng profiling/benchmark thích hợp và kết quả ngữ nghĩa làm chuẩn.

**Lỗi 15 — gọi terminal nhiều lần để có nhiều loại kết quả.** Một Stream không thể chạy count rồi toList. Nếu nguồn là Collection, tạo pipeline mới cho mỗi phép hoặc thiết kế một phép collect trả nhiều thống kê cùng lúc.

## 16. Checklist khi review một Stream pipeline

- **Nguồn là gì?** Collection, array, I/O hay generator? Có thể duyệt lại không?
- **Những bước nào là intermediate?** filter, map, sorted, distinct, limit, peek…
- **Có terminal operation không?** toList, count, collect, reduce, findFirst…
- **Callback được thực thi lúc nào?** Thường khi terminal yêu cầu đánh giá phần tử.
- **Có short-circuit hay tối ưu không?** count có thể không gọi map, findFirst có thể dừng sớm.
- **Có stateful operations không?** sorted và distinct có thể cần buffer.
- **Có side effects không?** Không phụ thuộc số lần gọi callback để thực hiện nghiệp vụ bắt buộc.
- **Stream có bị tái sử dụng không?** Mỗi instance chỉ dành cho một lượt tiêu thụ.
- **Nguồn có mutable không?** Tránh sửa nguồn trái hợp đồng; cân nhắc snapshot phù hợp.
- **Có xử lý I/O không?** Quản lý close và lỗi ở cả lúc mở nguồn lẫn khi terminal duyệt.
- **Có parallelism không?** Xem lại encounter order, concurrency và trạng thái chia sẻ.
- **Nguồn có vô hạn không?** Cần đảm bảo terminal có khả năng kết thúc.

## 17. Câu hỏi tự kiểm tra

1. Phân biệt giai đoạn xây dựng pipeline và giai đoạn terminal operation đánh giá phần tử.
2. Tại sao tạo Stream với filter/map chưa chắc đã gọi các lambda đó?
3. Vì sao toList cần dữ liệu đầu ra nhưng count có thể bỏ qua map trên nguồn List có size xác định?
4. Intermediate operation và terminal operation khác nhau về kiểu trả về thế nào?
5. Vì sao findFirst có thể kiểm tra ít phần tử hơn count?
6. Vì sao sorted có thể cần buffer dù pipeline vẫn lazy?
7. Tại sao không nên ghi audit trong peek?
8. Khi nào ngoại lệ của Integer.parseInt trong map có thể được phát sinh?
9. Sau pipeline.toList(), có được gọi pipeline.count() nữa không?
10. Nếu phải xử lý cùng List hai lần, làm thế nào tạo Stream mới?
11. Vì sao Files.lines có thể cần close ngay cả khi không có terminal operation?
12. Tại sao lazy không đồng nghĩa mọi lời gọi Java trong biểu thức xây dựng pipeline đều bị hoãn?
13. Stream.generate/iterate có thể tạo nguồn vô hạn; điều kiện gì giúp terminal kết thúc?
14. Với parallel stream, những kỳ vọng nào về thứ tự và số lần callback là không an toàn?
15. Vì sao filter/map không tự sửa Collection nguồn, và khi nào callback có thể gây mutation bất ngờ?
16. Viết lại một pipeline có side effect để kết quả nghiệp vụ không phụ thuộc số lần callback.

**Kết luận:** Java Stream **xây dựng pipeline bằng các thao tác trung gian trước**, rồi **đánh giá phần dữ liệu cần thiết khi có terminal operation**. Không phải mọi phần tử hoặc callback đều phải chạy trong mọi terminal, vì có short-circuit, tối ưu hóa và các phép có trạng thái. Nắm đúng thời điểm thực thi giúp dùng Stream dễ đọc, đúng hành vi, tránh tái sử dụng Stream, tránh side effects ẩn và quản lý tài nguyên I/O chính xác.