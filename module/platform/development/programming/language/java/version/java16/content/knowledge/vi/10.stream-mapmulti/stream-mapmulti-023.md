# Kiểm thử số lượng phát, thứ tự và tính tương đương của pipeline

Khi dùng Stream.mapMulti để biến một phần tử đầu vào thành không, một hoặc nhiều phần tử đầu ra, cần kiểm tra ba khía cạnh riêng: **số lượng phần tử được phát**, **thứ tự phát**, và **kết quả có tương đương với cách triển khai tham chiếu hay không**. Một pipeline có thể trả về đúng tập giá trị nhưng phát thiếu phần tử trùng lặp, đảo thứ tự hoặc xử lý sai trường hợp không phát phần tử.

mapMulti được giới thiệu trong Java 16 và vẫn là API Stream hiện hành. Bài học này tập trung vào cách viết test có tính xác định trên JDK hiện đại, so sánh với flatMap, kiểm tra stream tuần tự/song song và nhận diện những trường hợp hai pipeline không thể được xem là tương đương chỉ bằng cách so sánh danh sách kết quả.

## 1. Xác định hợp đồng đầu ra trước khi viết test

Với mỗi phần tử đầu vào, mapper của mapMulti có thể gọi Consumer:

- Không lần nào: phần tử đầu vào tạo ra 0 phần tử đầu ra.
- Một lần: phần tử đầu vào tạo ra đúng 1 phần tử.
- Nhiều lần: phần tử đầu vào tạo ra nhiều phần tử theo thứ tự gọi accept.

Ví dụ, quy tắc mở rộng một số nguyên n thành các số từ 0 đến n - 1:

~~~java
List<Integer> result = List.of(0, 1, 3, 2).stream()
        .<Integer>mapMulti((number, emit) -> {
            for (int i = 0; i < number; i++) {
                emit.accept(i);
            }
        })
        .toList();
~~~

Kết quả mong đợi là:

~~~text
[0, 0, 1, 2, 0, 1]
~~~

Phần tử đầu vào 0 không phát gì, 1 phát một giá trị, 3 phát ba giá trị và 2 phát hai giá trị. Tổng số phần tử đầu ra bằng tổng số lần mapper gọi Consumer, không nhất thiết bằng số phần tử đầu vào.

Trước khi viết test, hãy ghi rõ:

1. Với từng loại đầu vào, mapper phải phát bao nhiêu phần tử?
2. Nếu phát nhiều phần tử, thứ tự bên trong một lần mapper là gì?
3. Thứ tự giữa các phần tử đầu vào có cần được giữ không?
4. Phần tử trùng lặp có được giữ nguyên hay phải loại bỏ?
5. Pipeline có được phép chạy song song hoặc bỏ encounter order không?
6. Có quy tắc lọc, distinct, sort hoặc short-circuit ở downstream không?

## 2. Kiểm thử cardinality: 0, 1 và nhiều phần tử

Test cardinality phải bao phủ cả ba trường hợp. Chỉ kiểm tra trường hợp mỗi đầu vào phát một giá trị sẽ bỏ sót lỗi phổ biến như phát thừa, bỏ thiếu hoặc xử lý sai nhánh rỗng.

Ví dụ với JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

class MapMultiCardinalityTest {
    @Test
    void emitsZeroOneOrManyValues() {
        List<Integer> input = List.of(0, 1, 3, 2);

        List<Integer> actual = input.stream()
                .<Integer>mapMulti((number, emit) -> {
                    for (int i = 0; i < number; i++) {
                        emit.accept(i);
                    }
                })
                .toList();

        assertEquals(6, actual.size());
        assertEquals(List.of(0, 0, 1, 2, 0, 1), actual);
    }
}
~~~

Test này xác nhận cả tổng số phần tử lẫn giá trị và thứ tự. Nếu chỉ kiểm tra size, pipeline có thể phát sáu phần tử sai nội dung mà test vẫn pass.

### Tách từng trường hợp để thông báo lỗi rõ hơn

~~~java
@Test
void handlesEmptyExpansion() {
    List<Integer> actual = List.of(0, 0).stream()
            .<Integer>mapMulti((number, emit) -> {
                for (int i = 0; i < number; i++) {
                    emit.accept(i);
                }
            })
            .toList();

    assertEquals(List.of(), actual);
}

@Test
void handlesSingleExpansion() {
    List<Integer> actual = List.of(1).stream()
            .<Integer>mapMulti((number, emit) -> emit.accept(number * 10))
            .toList();

    assertEquals(List.of(10), actual);
}

@Test
void handlesMultipleExpansion() {
    List<Integer> actual = List.of(3).stream()
            .<Integer>mapMulti((number, emit) -> {
                for (int i = 1; i <= number; i++) {
                    emit.accept(i);
                }
            })
            .toList();

    assertEquals(List.of(1, 2, 3), actual);
}
~~~

Trong dự án thực tế, có thể gộp các trường hợp vào một test parameterized. Dù chọn cách nào, tên test và dữ liệu đầu vào nên cho biết rõ đang kiểm tra nhánh 0, 1 hay nhiều lần phát.

## 3. Kiểm tra công thức số lượng phần tử

Với một mapper xác định số phần tử phát ra theo từng đầu vào, có thể tính số lượng mong đợi độc lập với pipeline mapMulti.

Ví dụ, mỗi số nguyên dương n phát n phần tử:

~~~java
List<Integer> input = List.of(0, 1, 4, 2, 3);

long expectedCount = input.stream()
        .mapToLong(number -> Math.max(0, number))
        .sum();

long actualCount = input.stream()
        .<Integer>mapMulti((number, emit) -> {
            for (int i = 0; i < number; i++) {
                emit.accept(i);
            }
        })
        .count();

assertEquals(expectedCount, actualCount);
~~~

Công thức kỳ vọng phải được xây dựng từ quy tắc nghiệp vụ hoặc dữ liệu kiểm thử, không sao chép nguyên logic mapMulti sang phần tính expected. Nếu cả hai phía dùng cùng một vòng lặp sai, test có thể xác nhận sai lầm của chính implementation.

Với mapper phát theo điều kiện, viết rõ số lượng theo từng nhánh. Ví dụ mỗi số chẵn phát hai giá trị, số lẻ phát một giá trị:

~~~java
long expectedCount = input.stream()
        .mapToLong(number -> number % 2 == 0 ? 2 : 1)
        .sum();
~~~

Đừng dùng distinct hoặc Set khi mục tiêu là kiểm tra cardinality, vì các phần tử trùng lặp sẽ bị loại bỏ và làm sai số lượng cần xác nhận.

## 4. Kiểm thử thứ tự trong một lần mapper

Consumer được gọi nhiều lần theo thứ tự imperative trong thân mapper. Nếu mapper phát các giá trị theo vòng lặp, thứ tự đó là một phần của kết quả mong đợi.

~~~java
@Test
void preservesEmissionOrderWithinEachInput() {
    List<String> actual = List.of("A", "B").stream()
            .<String>mapMulti((value, emit) -> {
                emit.accept(value + "1");
                emit.accept(value + "2");
                emit.accept(value + "3");
            })
            .toList();

    assertEquals(
            List.of("A1", "A2", "A3", "B1", "B2", "B3"),
            actual);
}
~~~

Test này phát hiện các lỗi như đảo thứ tự phần tử trong vòng lặp, gọi Consumer ở nhánh không mong muốn, phát phần tử trước khi kiểm tra điều kiện hoặc dùng cấu trúc dữ liệu không giữ thứ tự khi chuẩn bị các giá trị cần phát.

Nếu thứ tự có ý nghĩa nghiệp vụ, hãy so sánh List đầy đủ thay vì chỉ so sánh Set.

## 5. Kiểm thử encounter order giữa các phần tử đầu vào

Với ordered stream, các intermediate operation như mapMulti duy trì encounter order. Khi dùng terminal operation giữ thứ tự như toList, kết quả phải phản ánh thứ tự nguồn và thứ tự phát trong từng mapper.

~~~java
@Test
void preservesEncounterOrderForOrderedSource() {
    List<Integer> input = List.of(3, 1, 2);

    List<String> actual = input.stream()
            .<String>mapMulti((number, emit) -> {
                emit.accept(number + "-first");
                emit.accept(number + "-second");
            })
            .toList();

    assertEquals(
            List.of(
                    "3-first", "3-second",
                    "1-first", "1-second",
                    "2-first", "2-second"),
            actual);
}
~~~

Không chỉ kiểm tra một nguồn List. Nếu ứng dụng dùng nguồn khác như LinkedHashSet, sorted stream, file lines hoặc một custom Spliterator, hãy xác định nguồn đó có encounter order hay không và kiểm thử đúng hợp đồng của nguồn.

### Ordered stream và unordered stream

unordered() cho phép pipeline bỏ yêu cầu encounter order để implementation có thêm tự do tối ưu. Sau khi gọi unordered, không nên viết test yêu cầu một thứ tự cụ thể.

Nếu thứ tự không phải hợp đồng, so sánh kết quả đã chuẩn hóa hoặc so sánh tần suất:

~~~java
List<Integer> actual = input.parallelStream()
        .unordered()
        .<Integer>mapMulti((number, emit) -> {
            emit.accept(number);
            emit.accept(number);
        })
        .sorted()
        .toList();

List<Integer> expected = input.stream()
        .flatMap(number -> java.util.stream.Stream.of(number, number))
        .sorted()
        .toList();

assertEquals(expected, actual);
~~~

Sort chỉ dùng được nếu phần tử có thứ tự tự nhiên hoặc có Comparator phù hợp. Nếu không thể sort, dùng Map đếm tần suất để kiểm tra multiset; cách này giữ được số lần xuất hiện của phần tử trùng lặp.

## 6. Phân biệt forEach và forEachOrdered trong test song song

Một ordered parallel stream vẫn có encounter order, nhưng terminal operation forEach không cam kết thực thi action theo thứ tự đó. Nếu test cần quan sát thứ tự, dùng toList hoặc forEachOrdered.

~~~java
@Test
void preservesEncounterOrderWhenCollectedFromParallelStream() {
    List<Integer> input = List.of(1, 2, 3, 4);

    List<Integer> actual = input.parallelStream()
            .<Integer>mapMulti((number, emit) -> {
                emit.accept(number);
                emit.accept(number * 10);
            })
            .toList();

    assertEquals(
            List.of(1, 10, 2, 20, 3, 30, 4, 40),
            actual);
}
~~~

Nếu cần ghi nhận bằng side effect trong terminal stage:

~~~java
List<Integer> observed = new java.util.ArrayList<>();

input.parallelStream()
        .<Integer>mapMulti((number, emit) -> {
            emit.accept(number);
            emit.accept(number * 10);
        })
        .forEachOrdered(observed::add);
~~~

forEachOrdered thực hiện action theo encounter order đối với ordered stream. Ngược lại, không dùng ArrayList thông thường để thu thập side effect từ forEach trên parallel stream; nhiều thread có thể gọi action đồng thời.

Một test không nên dựa vào việc forEach tình cờ giữ thứ tự trên máy phát triển. Nếu hợp đồng yêu cầu thứ tự, hãy dùng terminal operation có bảo đảm đó.

## 7. Kiểm tra phần tử trùng lặp và tần suất

mapMulti phát đúng những gì mapper yêu cầu. Nó không tự loại bỏ duplicate. Ví dụ:

~~~java
@Test
void preservesDuplicateEmissions() {
    List<Integer> actual = List.of(2, 2).stream()
            .<Integer>mapMulti((number, emit) -> {
                emit.accept(number);
                emit.accept(number);
            })
            .toList();

    assertEquals(List.of(2, 2, 2, 2), actual);
}
~~~

Nếu kết quả không có thứ tự nhưng duplicate vẫn quan trọng, có thể so sánh tần suất:

~~~java
Map<Integer, Long> frequencies = actual.stream()
        .collect(java.util.stream.Collectors.groupingBy(
                java.util.function.Function.identity(),
                java.util.stream.Collectors.counting()));
~~~

Test tần suất phát hiện trường hợp mapper phát thiếu hoặc thừa một giá trị ngay cả khi tập giá trị duy nhất không thay đổi. Ví dụ [A, A, B] và [A, B, B] có cùng Set là {A, B} nhưng khác số lần xuất hiện.

## 8. Dùng flatMap làm implementation tham chiếu

Vì mapMulti và flatMap cùng hỗ trợ một đầu vào tạo ra không hoặc nhiều đầu ra, có thể viết một implementation tham chiếu bằng flatMap rồi so sánh kết quả. Đây là cách hữu ích khi thay thế một pipeline cũ hoặc kiểm tra logic mở rộng phức tạp.

Ví dụ, mỗi số n tạo ra các số từ 0 đến n - 1:

~~~java
import java.util.List;
import java.util.stream.IntStream;

class ExpansionFunctions {
    static List<Integer> expandWithMapMulti(List<Integer> input) {
        return input.stream()
                .<Integer>mapMulti((number, emit) -> {
                    for (int i = 0; i < number; i++) {
                        emit.accept(i);
                    }
                })
                .toList();
    }

    static List<Integer> expandWithFlatMap(List<Integer> input) {
        return input.stream()
                .flatMap(number ->
                        IntStream.range(0, number).boxed())
                .toList();
    }
}
~~~

Test tương đương:

~~~java
@Test
void mapMultiMatchesFlatMapReference() {
    List<Integer> input = List.of(0, 1, 4, 2, 3);

    assertEquals(
            expandWithFlatMap(input),
            expandWithMapMulti(input));
}
~~~

Implementation tham chiếu nên độc lập về cách biểu diễn. Nếu cả hai pipeline gọi chung một helper có lỗi, phép so sánh không phát hiện được lỗi đó. Trong ví dụ trên, flatMap dùng IntStream.range, còn mapMulti dùng vòng lặp phát Consumer.

## 9. Kiểm thử tương đương với nhiều bộ dữ liệu xác định

Một test đơn lẻ có thể bỏ sót biên. Có thể tạo tập đầu vào nhỏ nhưng bao phủ các trường hợp 0, 1, nhiều phần tử, số âm nếu có trong domain và giá trị biên.

~~~java
@Test
void mapMultiMatchesFlatMapForManyInputRanges() {
    for (int upperBound = 0; upperBound <= 50; upperBound++) {
        List<Integer> input = IntStream.rangeClosed(0, upperBound)
                .boxed()
                .toList();

        assertEquals(
                expandWithFlatMap(input),
                expandWithMapMulti(input),
                "upperBound=" + upperBound);
    }
}
~~~

Đây là kiểu kiểm thử theo nhiều trường hợp dữ liệu có tính lặp lại, không cần thêm thư viện property-based. Nếu dự án dùng jqwik hoặc QuickTheories, có thể sinh dữ liệu ngẫu nhiên với seed cố định và thu nhỏ trường hợp lỗi; tuy nhiên, không cần thêm dependency chỉ để kiểm tra một mapper đơn giản.

Với dữ liệu có thể chứa số âm, hãy xác định hợp đồng trước. IntStream.range(0, number) phát rỗng khi number nhỏ hơn hoặc bằng 0; vòng lặp i < number cũng phát rỗng. Nếu domain yêu cầu ném exception cho số âm, cả implementation và expected reference phải kiểm tra cùng quy tắc đó.

## 10. So sánh cả pipeline, không chỉ mapper

Hai mapper có thể phát cùng dãy phần tử nhưng toàn pipeline vẫn khác nhau nếu các operation phía sau khác thứ tự hoặc có state.

Ví dụ, filter trước mapMulti khác với filter sau mapMulti:

~~~java
List<Integer> filterBefore = input.stream()
        .filter(number -> number > 0)
        .<Integer>mapMulti((number, emit) -> {
            emit.accept(number);
            emit.accept(number * number);
        })
        .toList();

List<Integer> filterAfter = input.stream()
        .<Integer>mapMulti((number, emit) -> {
            emit.accept(number);
            emit.accept(number * number);
        })
        .filter(number -> number > 0)
        .toList();
~~~

Nếu đầu vào có số âm, hai pipeline trên không cho cùng kết quả: filterBefore loại bỏ đầu vào âm hoàn toàn; filterAfter vẫn giữ bình phương dương do mapper phát ra. Hãy viết test theo đúng vị trí của từng operation.

Khi so sánh pipeline, cần giữ giống nhau:

- Thứ tự và điều kiện filter.
- distinct, sorted, limit và skip.
- Comparator và equality semantics của phần tử.
- Stream ordered hay unordered.
- Sequential hay parallel.
- Terminal operation và cách thu thập kết quả.

Không chỉ đổi mapMulti thành flatMap rồi giả định hai pipeline tương đương nếu các operation khác cũng đã được refactor.

## 11. Tương đương có giới hạn khi có side effect

Stream pipeline nên dùng mapper stateless và non-interfering. Không nên dựa vào số lần gọi mapper, thứ tự thread hoặc side effect bên trong mapper để xác định kết quả nghiệp vụ.

Ví dụ sau là test dễ gây nhầm:

~~~java
AtomicInteger calls = new AtomicInteger();

List<Integer> result = input.stream()
        .<Integer>mapMulti((number, emit) -> {
            calls.incrementAndGet();
            emit.accept(number);
        })
        .toList();
~~~

Đếm số lần mapper được gọi có thể hữu ích khi điều tra một implementation cụ thể, nhưng không nên biến nó thành hợp đồng ứng dụng trừ khi API thật sự quy định số lần đánh giá. Các intermediate operation có side effect không phải nơi an toàn để đặt logic cần được thực thi chính xác một lần.

Tương tự, không sửa collection nguồn hoặc trạng thái được dùng trong predicate/mapper khi pipeline đang chạy. Việc can thiệp nguồn có thể gây kết quả không xác định hoặc lỗi concurrent modification.

Khi so sánh mapMulti với flatMap, hãy ưu tiên mapper thuần: cùng input luôn tạo cùng dãy output, không ghi trạng thái bên ngoài, không phụ thuộc thread và không thay đổi nguồn.

## 12. Short-circuit: kết quả bằng nhau chưa chắc chi phí thực thi bằng nhau

mapMulti nhận Consumer để mapper phát phần tử. Consumer không có API cho mapper hỏi downstream đã dừng hay chưa. Nếu mapper chạy một vòng lặp và phát rất nhiều phần tử, downstream limit(1) không phải là tín hiệu để vòng lặp imperative đó tự dừng giữa chừng.

~~~java
List<Integer> actual = Stream.of(100_000)
        .<Integer>mapMulti((number, emit) -> {
            for (int i = 0; i < number; i++) {
                emit.accept(i);
            }
        })
        .limit(1)
        .toList();
~~~

Kết quả chỉ có một phần tử, nhưng mapper có thể đã gọi Consumer rất nhiều lần trước khi pipeline hoàn tất xử lý đầu vào hiện tại. Vì thế, test chỉ kiểm tra kết quả của limit không chứng minh rằng mapper dừng sớm.

Với flatMap, mapper trả về Stream con. Stream pipeline có thể truyền yêu cầu short-circuit vào quá trình duyệt Stream con, vì vậy việc duyệt có thể dừng sớm tự nhiên hơn. Hành vi và mức tiết kiệm thực tế vẫn cần được đo trên implementation và pipeline cụ thể.

Nếu số phần tử phát ra có thể rất lớn, hãy cân nhắc:

- Đặt giới hạn ngay trong mapper trước khi gọi Consumer.
- Dùng flatMap khi dữ liệu đã là Stream con và cần short-circuit xuyên xuống nguồn.
- Dùng API chuyên biệt có hỗ trợ cancellation/backpressure nếu bài toán cần điều khiển luồng.
- Tránh tạo một dãy khổng lồ trong mapper chỉ để downstream loại bỏ gần hết.

## 13. Kiểm thử exception và đầu vào biên

Test nên xác nhận hành vi khi mapper không thể phát kết quả:

- Đầu vào rỗng.
- Đầu vào null nếu hợp đồng cho phép hoặc từ chối rõ ràng.
- Giá trị biên như 0, số âm, số rất lớn.
- Mapper phát một vài giá trị rồi ném exception.
- Downstream operation ném exception.

Ví dụ, nếu quy tắc domain yêu cầu từ chối số âm:

~~~java
@Test
void rejectsNegativeInput() {
    assertThrows(IllegalArgumentException.class, () ->
            Stream.of(-1)
                    .<Integer>mapMulti((number, emit) -> {
                        if (number < 0) {
                            throw new IllegalArgumentException(
                                    "number must not be negative");
                        }
                        emit.accept(number);
                    })
                    .toList());
}
~~~

Nếu mapper đã phát một phần tử rồi ném exception, terminal operation không trả về một List một phần. Pipeline thất bại và exception truyền ra. Không nên kiểm tra trạng thái collection ngoài được sửa trong mapper như một cách thu kết quả một phần; đó là side effect làm test khó dự đoán.

## 14. Bộ test mẫu: cardinality, order và flatMap equivalence

Ví dụ hoàn chỉnh sau gom các kiểm tra chính vào một test class:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class MapMultiPipelineTest {
    private static List<Integer> mapMulti(List<Integer> input) {
        return input.stream()
                .<Integer>mapMulti((number, emit) -> {
                    for (int i = 0; i < number; i++) {
                        emit.accept(i);
                    }
                })
                .toList();
    }

    private static List<Integer> flatMap(List<Integer> input) {
        return input.stream()
                .flatMap(number ->
                        IntStream.range(0, number).boxed())
                .toList();
    }

    @Test
    void checksCardinalityAndEmissionOrder() {
        List<Integer> input = List.of(0, 1, 3, 2);

        List<Integer> actual = mapMulti(input);

        assertEquals(6, actual.size());
        assertEquals(List.of(0, 0, 1, 2, 0, 1), actual);
    }

    @Test
    void matchesFlatMapReference() {
        List<Integer> input = List.of(0, 1, 4, 2, 3);

        assertEquals(flatMap(input), mapMulti(input));
    }

    @Test
    void preservesOrderForParallelOrderedStream() {
        List<Integer> input = List.of(3, 1, 2);

        List<Integer> actual = input.parallelStream()
                .<Integer>mapMulti((number, emit) -> {
                    for (int i = 0; i < number; i++) {
                        emit.accept(number * 10 + i);
                    }
                })
                .toList();

        assertEquals(
                List.of(30, 31, 32, 10, 20, 21),
                actual);
    }

    @Test
    void matchesReferenceAcrossInputRanges() {
        for (int upperBound = 0; upperBound <= 50; upperBound++) {
            List<Integer> input = IntStream.rangeClosed(0, upperBound)
                    .boxed()
                    .toList();

            assertEquals(flatMap(input), mapMulti(input));
        }
    }
}
~~~

Các test này chạy trên Java 16 trở lên vì sử dụng mapMulti và Stream.toList. Nếu dự án cần hỗ trợ JDK thấp hơn Java 16, không thể biên dịch trực tiếp test gọi mapMulti trên JDK đó; hãy chạy test bằng toolchain JDK có API tương ứng.

## 15. Checklist review test cho mapMulti

- [ ] Có test mapper phát 0 phần tử.
- [ ] Có test mapper phát đúng 1 phần tử.
- [ ] Có test mapper phát nhiều phần tử.
- [ ] Cardinality được kiểm tra bằng số lượng chính xác.
- [ ] Nội dung và thứ tự phát trong mỗi mapper được kiểm tra.
- [ ] Encounter order giữa các input được kiểm tra khi nguồn có thứ tự.
- [ ] Duplicate được giữ hoặc loại bỏ theo đúng hợp đồng.
- [ ] Parallel ordered stream dùng terminal operation giữ thứ tự khi cần.
- [ ] Unordered stream được so sánh bằng tập/tần suất thay vì thứ tự tùy ý.
- [ ] Có implementation tham chiếu độc lập bằng flatMap khi phù hợp.
- [ ] Test nhiều bộ dữ liệu biên và trường hợp rỗng.
- [ ] Pipeline được so sánh với cùng filter/sort/distinct/limit và terminal operation.
- [ ] Mapper không phụ thuộc side effect, shared mutable state hoặc thread order.
- [ ] Nếu dùng short-circuit, đã kiểm tra lượng công việc mapper thực sự thực hiện.
- [ ] Exception và trường hợp đầu vào không hợp lệ có test riêng.

## 16. Ghi nhớ

- mapMulti có thể phát 0, 1 hoặc nhiều phần tử cho mỗi input.
- Cardinality là tổng số lần Consumer được gọi; không nhất thiết bằng số input.
- Với ordered stream, hãy kiểm tra cả thứ tự giữa input và thứ tự emit trong mapper.
- Parallel stream vẫn có encounter order nếu nguồn ordered và pipeline không bỏ order; dùng toList hoặc forEachOrdered để quan sát thứ tự.
- forEach không cam kết action theo encounter order trên parallel stream.
- Không dùng Set hoặc distinct khi cần kiểm tra số lần xuất hiện của duplicate.
- flatMap là implementation tham chiếu hữu ích nếu mapper thuần và hai pipeline có cùng quy tắc phát.
- So sánh cả pipeline, không chỉ mapper; vị trí filter, sort, distinct và limit có thể làm đổi kết quả.
- mapMulti và flatMap không nhất thiết có cùng chi phí khi downstream short-circuit.
- Tránh side effect trong mapper; test hành vi đầu ra thay vì giả định số lần đánh giá nội bộ.

Kiểm thử mapMulti tốt cần xác nhận cả số lượng, thứ tự và nội dung đầu ra. Dùng flatMap làm implementation tham chiếu cho mapper thuần, kiểm thử ordered/parallel đúng hợp đồng và giữ riêng các test cho short-circuit sẽ giúp refactor Stream pipeline an toàn hơn trên các JDK hiện đại.

## Tài liệu tham khảo

- [Java 25 Stream API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html) — hợp đồng mapMulti, flatMap, encounter order và terminal operations.
- [Java 25 Stream package summary](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html) — stateless/non-interfering behavioral parameters, ordering và parallel execution.
