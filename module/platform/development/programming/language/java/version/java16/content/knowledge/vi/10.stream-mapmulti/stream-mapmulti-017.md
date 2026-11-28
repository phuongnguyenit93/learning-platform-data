# Giới hạn vòng đời consumer và cấm giữ lại để phát bất đồng bộ

Trong `Stream.mapMulti`, mapper nhận một phần tử nguồn và một `Consumer` để phát không, một hoặc nhiều phần tử đầu ra. Consumer này chỉ hợp lệ trong thời gian mapper hiện tại đang được thực thi. Mapper phải gọi `accept` đồng bộ trước khi kết thúc; không được giữ Consumer để gọi sau, chuyển nó sang thread khác hoặc đăng ký làm callback bất đồng bộ.

Quy tắc này cũng áp dụng cho các biến thể primitive: `mapMultiToInt` dùng `IntConsumer`, `mapMultiToLong` dùng `LongConsumer`, `mapMultiToDouble` dùng `DoubleConsumer`; các primitive Stream có mapper chuyên biệt như `IntMapMultiConsumer`, `LongMapMultiConsumer` và `DoubleMapMultiConsumer`. Consumer là kênh phát dữ liệu thuộc lần gọi mapper hiện tại, không phải một publisher hay callback có thể tái sử dụng.

## 1. Consumer downstream thuộc về một lần gọi mapper

Chữ ký tổng quát của `Stream<T>.mapMulti`:

```java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

Với mỗi phần tử nguồn, Stream gọi mapper và truyền vào:

1. Phần tử nguồn hiện tại kiểu `T`.
2. Consumer downstream nhận phần tử đầu ra kiểu `R`.

Mapper có thể gọi `accept` không lần nào, một lần hoặc nhiều lần. Các lần gọi này phải diễn ra trong chính lần thực thi mapper đó:

```java
List<String> labels = products.stream()
    .<String>mapMulti((product, emit) -> {
        emit.accept(product.name());
        emit.accept("sku=" + product.sku());
    })
    .toList();
```

Khi mapper xử lý một sản phẩm, nó phát tên và SKU label ngay trong callback. Sau khi lambda trả về, Stream có thể tiếp tục xử lý pipeline, kết thúc một phần công việc hoặc chuyển sang phần tử nguồn khác. Consumer đã nhận không còn được phép sử dụng.

Hãy xem Consumer như một tham số callback tạm thời. Nó được Stream cung cấp để mapper chuyển kết quả vào phần tiếp theo của pipeline trong lúc mapper đang chạy.

## 2. Vì sao không được giữ Consumer sau khi mapper kết thúc?

Stream API quy định Consumer chỉ có hiệu lực trong thời gian thực thi mapper. Nếu mapper giữ lại Consumer và gọi nó sau khi mapper đã trả về, hành vi là không xác định.

Điều này có nghĩa chương trình không thể dựa vào bất kỳ kết quả cụ thể nào. Có thể một thử nghiệm nhỏ tình cờ chạy được, nhưng chương trình không còn tuân theo hợp đồng API và có thể hỏng khi đổi JDK, đổi cách triển khai pipeline hoặc chuyển sang parallel Stream.

Không giữ Consumer trong:

- Field của object hoặc biến static.
- Collection, queue hoặc cache để phát sau.
- Một đối tượng được trả về từ mapper.
- `CompletableFuture`, callback, listener hoặc continuation chạy sau.
- Tác vụ gửi qua `Executor`, thread hoặc scheduler.
- Một tác vụ được lưu lại để chạy sau khi terminal operation kết thúc.

Không gọi Consumer sau khi callback kết thúc, kể cả khi biến tham chiếu vẫn còn tồn tại và chương trình vẫn biên dịch.

## 3. Cách đúng: phát kết quả đồng bộ ngay trong mapper

Ví dụ, một tài liệu có nhiều từ. Mapper duyệt danh sách từ và phát từng từ hợp lệ trước khi trả về:

```java
import java.util.List;

record Document(String title, List<String> words) {}

List<Document> documents = List.of(
    new Document("Java", List.of("record", "stream", "mapMulti")),
    new Document("JVM", List.of("memory", "thread"))
);

List<String> allWords = documents.stream()
    .<String>mapMulti((document, emit) -> {
        for (String word : document.words()) {
            if (!word.isBlank()) {
                emit.accept(word);
            }
        }
    })
    .toList();
```

Vòng lặp chạy đồng bộ trong mapper. Mỗi từ được phát ngay khi được duyệt. Khi lambda kết thúc, không còn lời gọi nào giữ lại để phát về sau.

Đây là cách sử dụng phù hợp: mapper tạo kết quả và gửi chúng vào Consumer trong cùng một lần gọi.

## 4. Tách helper method vẫn hợp lệ nếu helper dùng Consumer đồng bộ

Có thể tách logic phát dữ liệu thành phương thức riêng để mapper ngắn gọn hơn. Điều kiện là helper phải sử dụng Consumer ngay trong lời gọi và không lưu nó để sử dụng sau.

```java
import java.util.List;
import java.util.function.Consumer;

record Document(String title, List<String> words) {}

class DocumentMapper {
    static void emitWords(
        Document document,
        Consumer<String> downstream
    ) {
        for (String word : document.words()) {
            if (!word.isBlank()) {
                downstream.accept(word);
            }
        }
    }

    static List<String> collectWords(List<Document> documents) {
        return documents.stream()
            .<String>mapMulti(DocumentMapper::emitWords)
            .toList();
    }
}
```

`DocumentMapper.emitWords` chỉ sử dụng Consumer trong lúc phương thức đang chạy. Khi helper trả về, mapper cũng kết thúc và Consumer không được giữ lại.

Việc truyền Consumer qua một hoặc nhiều helper method đồng bộ không tự nó là vấn đề. Điều cần tránh là để Consumer thoát khỏi phạm vi thực thi của mapper, chẳng hạn gán vào field, đưa vào queue hoặc chuyển sang callback sẽ chạy sau.

## 5. Cách sai: lưu Consumer vào collection để phát sau

Đoạn mã dưới đây có thể biên dịch nhưng vi phạm hợp đồng của `mapMulti`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

record Document(String title) {}

List<Document> documents = List.of(
    new Document("Java"),
    new Document("JVM")
);

List<Consumer<String>> savedConsumers = new ArrayList<>();

documents.stream()
    .<String>mapMulti((document, emit) -> {
        savedConsumers.add(emit);
    })
    .toList();

// Không hợp lệ: các Consumer đã được giữ lại sau khi mapper kết thúc.
savedConsumers.forEach(emit -> emit.accept("late value"));
```

`savedConsumers` giữ các Consumer sau khi mapper trả về. Lệnh gọi `accept` ở cuối xảy ra ngoài thời gian hiệu lực của các Consumer đó, vì vậy hành vi không xác định.

Không sửa vấn đề bằng cách giữ collection sống lâu hơn, đồng bộ hóa nó hoặc bảo đảm terminal operation đã kết thúc. Consumer vẫn không còn hiệu lực sau mapper invocation.

## 6. Cách sai: gửi Consumer vào Executor

Không đưa Consumer vào tác vụ chạy nền:

Tiếp tục dùng `Document` và danh sách `documents` đã khai báo ở mục 5. Executor trong ví dụ được lấy từ common pool:

```java
import java.util.concurrent.Executor;
import java.util.concurrent.ForkJoinPool;

Executor executor = ForkJoinPool.commonPool();

documents.stream()
    .<String>mapMulti((document, emit) -> {
        executor.execute(() -> {
            emit.accept(document.title());
        });
    })
    .toList();
```

Tác vụ được Executor lên lịch có thể chạy sau khi lambda đã trả về. Khi đó nó gọi Consumer ngoài thời gian hợp lệ.

Ngay cả khi tác vụ thường chạy rất nhanh và có vẻ hoàn tất trước khi mapper trả về, cách viết này vẫn dựa vào lịch chạy của thread khác và không bảo đảm Consumer được gọi đúng trong phạm vi mapper. Cũng không gọi cùng một Consumer đồng thời từ nhiều thread.

`mapMulti` không biến một callback đồng bộ thành cơ chế phát dữ liệu bất đồng bộ. Việc gọi `accept` phải nằm trong lần gọi mapper; Executor không thể kéo dài vòng đời Consumer.

## 7. Cách sai: capture Consumer trong CompletableFuture hoặc callback

Các continuation của `CompletableFuture` có thể chạy sau khi mapper kết thúc. Vì vậy không capture Consumer trong chúng:

Ví dụ cũng dùng `documents` từ mục 5:

```java
import java.util.concurrent.CompletableFuture;

documents.stream()
    .<String>mapMulti((document, emit) -> {
        CompletableFuture
            .supplyAsync(document::title)
            .thenAccept(emit);
    })
    .toList();
```

`thenAccept(emit)` lưu Consumer làm hành động hoàn tất. Khi future hoàn thành, callback có thể được gọi sau khi mapper đã trả về. Đây là việc sử dụng Consumer ngoài thời gian hiệu lực.

Quy tắc tương tự áp dụng cho:

- `thenApply` hoặc `thenAccept`.
- `whenComplete` và `handle`.
- Listener đăng ký vào event source.
- Callback của timer hoặc scheduler.
- Reactive subscription và callback của thư viện I/O.

Không truyền Consumer downstream của `mapMulti` cho bất kỳ cơ chế nào có thể gọi nó sau callback hiện tại.

## 8. Nếu cần xử lý bất đồng bộ, hãy hoàn thành tác vụ trước rồi phát kết quả

Khi công việc cần thực hiện bất đồng bộ, hãy để mỗi tác vụ trả về dữ liệu của chính nó. Sau đó kết hợp kết quả bằng `CompletableFuture`. Consumer của `mapMulti` không tham gia vào các tác vụ nền.

Ví dụ, mỗi tài liệu được phân tích bất đồng bộ thành danh sách từ. Sau khi các future hoàn tất, kết quả được làm phẳng thành một danh sách:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.stream.Stream;

record Document(String title, String text) {}

class AsyncTokenizer {
    static List<String> tokenize(Document document) {
        return Stream.of(document.text().split("\\s+"))
            .filter(token -> !token.isBlank())
            .toList();
    }

    static CompletableFuture<List<String>> tokenizeAll(
        List<Document> documents,
        Executor executor
    ) {
        List<CompletableFuture<List<String>>> tasks = documents.stream()
            .map(document -> CompletableFuture.supplyAsync(
                () -> tokenize(document),
                executor
            ))
            .toList();

        CompletableFuture<?>[] taskArray =
            tasks.toArray(new CompletableFuture<?>[0]);
        CompletableFuture<Void> allTasks = CompletableFuture.allOf(taskArray);

        return allTasks.thenApply(ignored ->
            tasks.stream()
                .flatMap(task -> task.join().stream())
                .toList()
        );
    }
}
```

Mỗi future sở hữu kết quả riêng là `List<String>`. `allOf` đợi các tác vụ hoàn tất; sau đó pipeline lấy kết quả đã hoàn thành và làm phẳng chúng.

Không có Consumer downstream nào bị giữ lại. Nếu cần sử dụng `mapMulti` ở bước sau, hãy gọi nó trên danh sách kết quả đã sẵn sàng và phát đồng bộ trong mapper:

Tiếp tục dùng record `Document` và lớp `AsyncTokenizer` đã khai báo ở trên. Khởi tạo nguồn và Executor, chờ kết quả bất đồng bộ rồi mới dùng Stream:

```java
import java.util.List;
import java.util.concurrent.Executor;
import java.util.concurrent.ForkJoinPool;

List<Document> documents = List.of(
    new Document("Java", "stream record mapper"),
    new Document("JVM", "thread memory")
);
Executor executor = ForkJoinPool.commonPool();

List<String> completedWords = AsyncTokenizer.tokenizeAll(documents, executor).join();

List<String> uniqueWords = completedWords.stream()
    .<String>mapMulti((word, emit) -> {
        if (!word.isBlank()) {
            emit.accept(word.trim());
        }
    })
    .distinct()
    .toList();
```

Trong ví dụ này, `completedWords` là dữ liệu đã có sẵn sau khi các tác vụ bất đồng bộ hoàn tất. `mapMulti` chỉ thực hiện biến đổi đồng bộ trên dữ liệu đó.

## 9. Nếu chỉ cần chạy xử lý bất đồng bộ trên từng phần tử, trả về future thay vì giữ Consumer

Một thiết kế khác là để Stream tạo ra các future. Mỗi phần tử nguồn tạo một future; pipeline sau đó có thể kết hợp chúng:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ForkJoinPool;

record Document(String title, List<String> words) {}

List<Document> documents = List.of(
    new Document("Java", List.of("stream", "record")),
    new Document("JVM", List.of("thread", "memory"))
);
Executor executor = ForkJoinPool.commonPool();

List<CompletableFuture<String>> titleTasks = documents.stream()
    .map(document -> CompletableFuture.supplyAsync(
        document::title,
        executor
    ))
    .toList();
```

Ở đây, `map` trả về một `CompletableFuture<String>` cho mỗi tài liệu. Future là kết quả thực sự của phép biến đổi và có vòng đời riêng; không có Consumer của `mapMulti` được giữ lại.

Khi một phần tử cần tạo nhiều tác vụ, có thể tạo danh sách future cho phần tử đó rồi làm phẳng danh sách bằng `flatMap`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ForkJoinPool;

record Document(String title, List<String> words) {}

List<Document> documents = List.of(
    new Document("Java", List.of("stream", "record")),
    new Document("JVM", List.of("thread", "memory"))
);
Executor executor = ForkJoinPool.commonPool();

List<CompletableFuture<String>> tasks = documents.stream()
    .flatMap(document -> document.words().stream()
        .map(word -> CompletableFuture.supplyAsync(
            word::toUpperCase,
            executor
        )))
    .toList();
```

Cách này biểu diễn rõ rằng dữ liệu được tạo ra là các tác vụ bất đồng bộ. Hãy kết hợp hoặc chờ future ở một bước riêng theo yêu cầu của ứng dụng.

## 10. mapMulti và parallel Stream không đồng nghĩa với phát bất đồng bộ

`parallelStream()` cho phép Stream framework xử lý các phần tử nguồn song song. Đây là cơ chế thực thi do Stream quản lý, không phải quyền giữ Consumer và gọi nó sau mapper.

Ví dụ hợp lệ:

```java
import java.util.List;

List<Integer> expanded = List.of(1, 2, 3)
    .parallelStream()
    .<Integer>mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 10);
    })
    .toList();
```

Mỗi mapper gọi Consumer đồng bộ trong chính lần thực thi của nó. Framework có thể chạy các mapper của những phần tử nguồn khác nhau trên các thread khác nhau, nhưng mapper không tự chuyển Consumer của nó sang một tác vụ chạy sau.

Với nguồn có encounter order, các thao tác kết quả có thứ tự như `toList()` bảo toàn encounter order. Không dựa vào thứ tự thread bắt đầu hoặc kết thúc để thực hiện tác dụng phụ.

Không chia sẻ một Consumer nhận từ mapper cho nhiều thread và không tạo các tác vụ nền cùng gọi Consumer đó. Nếu cần song song hóa công việc, hãy để mỗi tác vụ trả về kết quả độc lập rồi kết hợp chúng qua Stream hoặc CompletableFuture.

## 11. Short-circuit có thể làm pipeline ngừng tiêu thụ sớm

Các terminal operation như `findFirst()`, `findAny()`, `anyMatch()`, `allMatch()` hoặc `noneMatch()` có thể kết thúc mà không cần tiêu thụ toàn bộ nguồn.

Ví dụ:

```java
import java.util.List;
import java.util.Optional;

List<List<String>> groups = List.of(
    List.of("alpha", "beta"),
    List.of("target", "delta"),
    List.of("omega")
);

Optional<String> found = groups.stream()
    .<String>mapMulti((group, emit) -> {
        for (String value : group) {
            emit.accept(value);
        }
    })
    .filter("target"::equals)
    .findFirst();
```

Khi tìm được `target`, pipeline có thể ngừng yêu cầu các phần tử nguồn tiếp theo. Tuy nhiên, không dựa vào `findFirst()` để ngắt vòng lặp bên trong mapper giữa chừng: mapper có thể hoàn tất việc phát các giá trị của phần tử nguồn hiện tại trước khi downstream áp dụng short-circuit. Stream không truyền tín hiệu hủy vào vòng lặp của mapper.

Điều này càng cho thấy Consumer không phải một kênh sự kiện để lưu lại và phát đủ kết quả vào thời điểm khác. Consumer chỉ phục vụ lần mapper hiện tại; pipeline quyết định khi nào tiêu thụ và khi nào dừng.

Không dùng tác dụng phụ trong mapper để bảo đảm mọi phần tử đều được xử lý. Nếu yêu cầu nghiệp vụ là xử lý tất cả phần tử, hãy chọn terminal operation tiêu thụ toàn bộ nguồn và giữ logic xử lý có tác dụng phụ ở một bước phù hợp.

## 12. Consumer primitive cũng có cùng giới hạn vòng đời

Các biến thể primitive thay đổi kiểu dữ liệu nhận và phát, nhưng không thay đổi quy tắc vòng đời.

| Phương thức | Mapper | Consumer phát kết quả |
|---|---|---|
| `Stream<T>.mapMulti` | `BiConsumer<? super T, ? super Consumer<R>>` | `Consumer<R>` |
| `Stream<T>.mapMultiToInt` | `BiConsumer<? super T, ? super IntConsumer>` | `IntConsumer` |
| `Stream<T>.mapMultiToLong` | `BiConsumer<? super T, ? super LongConsumer>` | `LongConsumer` |
| `Stream<T>.mapMultiToDouble` | `BiConsumer<? super T, ? super DoubleConsumer>` | `DoubleConsumer` |
| `IntStream.mapMulti` | `IntMapMultiConsumer` | `IntConsumer` |
| `LongStream.mapMulti` | `LongMapMultiConsumer` | `LongConsumer` |
| `DoubleStream.mapMulti` | `DoubleMapMultiConsumer` | `DoubleConsumer` |

Ví dụ đúng với primitive Consumer:

```java
import java.util.stream.IntStream;

int[] digits = IntStream.of(12, 305)
    .mapMulti((number, emit) -> {
        for (int value = number; value > 0; value /= 10) {
            emit.accept(value % 10);
        }
    })
    .toArray();
```

`emit` có kiểu `IntConsumer`. Các lời gọi `accept(int)` diễn ra trong vòng lặp của mapper và hoàn tất trước khi mapper trả về.

Không lưu `IntConsumer`, `LongConsumer` hoặc `DoubleConsumer` để phát từ tác vụ bất đồng bộ. Việc dùng primitive type không kéo dài vòng đời của Consumer.

## 13. Đừng nhầm Consumer với kết quả có thể lưu trữ

Nếu cần lưu dữ liệu để sử dụng sau, hãy lưu chính dữ liệu đã tạo ra, không lưu Consumer do Stream cung cấp.

Ví dụ, có thể thu các kết quả vào collection bằng terminal operation:

Dùng `Document` và `documents` đã khai báo ở mục 3:

```java
List<String> tokens = documents.stream()
    .<String>mapMulti((document, emit) -> {
        for (String token : document.words()) {
            emit.accept(token);
        }
    })
    .toList();
```

Sau khi terminal operation hoàn tất, `tokens` là danh sách kết quả độc lập có thể được lưu, truyền sang thread khác hoặc xử lý sau theo quy tắc đồng bộ của ứng dụng.

Sự khác biệt:

- **Dữ liệu kết quả** như `String`, `Integer` hoặc record là giá trị do ứng dụng sở hữu.
- **Consumer downstream** là callback tạm thời do Stream cung cấp để đưa dữ liệu vào pipeline.
- Có thể lưu dữ liệu kết quả sau khi phát; không giữ Consumer để phát dữ liệu sau.

Nếu cần gửi dữ liệu ra queue hoặc event bus, hãy gửi giá trị kết quả trong hoặc sau terminal operation bằng API phù hợp, không gửi Consumer của mapper.

## 14. Những lưu ý khi thiết kế mapper

Một mapper dễ kiểm soát vòng đời Consumer thường có các đặc điểm:

- Phát kết quả ngay trong thân mapper.
- Không gán Consumer vào field hoặc collection.
- Không trả Consumer từ helper method.
- Helper nhận Consumer chỉ thực hiện phát đồng bộ rồi trả về.
- Không tạo thread, future hoặc callback để gọi Consumer sau.
- Không chia sẻ Consumer cho nhiều thread.
- Không dựa vào mapper được gọi đúng một lần để thực hiện tác dụng phụ.
- Không dựa vào việc pipeline sẽ tiêu thụ toàn bộ phần tử khi terminal operation có thể short-circuit.

Nếu logic phát dữ liệu cần một trạng thái hoặc một luồng sự kiện tồn tại lâu dài, hãy mô hình hóa trạng thái hoặc event stream bằng API có vòng đời phù hợp. `mapMulti` chỉ là một thao tác trung gian trong một Stream pipeline hữu hạn.

## 15. Lỗi thường gặp

**Lưu Consumer vào field hoặc collection.** Consumer không còn hợp lệ sau khi mapper trả về. Hãy lưu dữ liệu đầu ra nếu cần dùng về sau.

**Gọi accept trong Executor.** Tác vụ có thể chạy sau mapper invocation hoặc từ thread khác. Hãy để tác vụ trả về dữ liệu riêng và kết hợp kết quả sau.

**Capture Consumer trong CompletableFuture.** Continuation có thể được thực thi sau khi mapper kết thúc. Không truyền Consumer vào future, listener hoặc callback.

**Nghĩ rằng parallelStream cho phép phát bất đồng bộ.** Parallel Stream do framework quản lý; mapper vẫn phải gọi Consumer trong lần gọi hiện tại.

**Truyền Consumer cho helper rồi helper giữ lại.** Helper đồng bộ có thể dùng Consumer; helper không được lưu hoặc chuyển nó sang callback chạy sau.

**Dựa vào findFirst hoặc anyMatch để chạy mọi mapper.** Short-circuit có thể dừng pipeline sớm. Không dùng mapper để bảo đảm tác dụng phụ cho toàn bộ nguồn.

**Nhầm dữ liệu kết quả với Consumer.** Có thể lưu danh sách giá trị đã thu thập; không lưu callback downstream do Stream cấp.

**Cho rằng mã chạy được nghĩa là hợp lệ.** Việc Consumer vẫn có thể được gọi qua một tham chiếu không chứng minh rằng nó còn hiệu lực theo hợp đồng API.

## 16. Ghi nhớ

- Consumer được truyền vào mapper chỉ hợp lệ trong thời gian mapper invocation hiện tại.
- Gọi `accept` đồng bộ không, một hoặc nhiều lần trước khi mapper trả về.
- Không lưu Consumer vào field, collection, queue hoặc đối tượng trả về.
- Không chuyển Consumer sang Executor, thread, CompletableFuture, listener hoặc callback bất đồng bộ.
- Có thể truyền Consumer cho helper method nếu helper dùng nó đồng bộ và không giữ lại.
- Parallel Stream không làm thay đổi quy tắc vòng đời Consumer.
- Short-circuit operation có thể ngừng tiêu thụ pipeline sớm; không giả định mọi mapper đều chạy.
- Nếu cần bất đồng bộ, hãy để tác vụ trả về dữ liệu hoặc future riêng rồi kết hợp kết quả; không phát qua Consumer của mapper sau callback.
- Quy tắc tương tự áp dụng cho `Consumer` generic và các primitive Consumer như `IntConsumer`, `LongConsumer`, `DoubleConsumer`.

`mapMulti` là cách phát không, một hoặc nhiều kết quả trong một mapper đồng bộ. Giữ Consumer trong đúng phạm vi callback giúp pipeline tuân thủ hợp đồng Stream, tránh phụ thuộc vào lịch chạy thread và tránh hành vi không xác định khi phát dữ liệu muộn.

