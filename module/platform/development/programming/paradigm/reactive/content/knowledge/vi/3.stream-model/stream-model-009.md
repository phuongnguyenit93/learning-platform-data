# Phân biệt luồng phản ứng với Java Stream và bộ sưu tập

## Ba khái niệm giải quyết ba nhu cầu khác nhau

Trong Java, `Collection`, `Stream` thuộc `java.util.stream` và luồng phản ứng (reactive stream) đều có thể xuất hiện trong một đoạn mã xử lý nhiều phần tử. Tuy nhiên, chúng không phải ba cách gọi cho cùng một thứ. Mỗi khái niệm tập trung vào một vấn đề riêng:

- **Bộ sưu tập (collection)** là cấu trúc dữ liệu dùng để lưu giữ và quản lý các phần tử. Ví dụ: `List`, `Set` và `Queue`. `Map` cũng thuộc Java Collections Framework nhưng là một abstraction riêng, không triển khai interface `Collection`.
- **Java Stream** là cách mô tả một phép tính xử lý dữ liệu từ một nguồn thông qua các bước như lọc, ánh xạ và tổng hợp. Stream API thuộc `java.util.stream`.
- **Luồng phản ứng (reactive stream)** là mô hình xử lý chuỗi tín hiệu hoặc phần tử được phát theo thời gian, có hợp đồng đăng ký, truyền dữ liệu, kết thúc và điều tiết nhu cầu. Trong Java, Reactive Streams định nghĩa giao thức `Publisher`–`Subscriber`; Project Reactor cung cấp `Flux` và `Mono` để xây dựng pipeline theo mô hình này.

Điểm khác biệt quan trọng nằm ở cách dữ liệu tồn tại, cách pipeline được kích hoạt, cách bên nhận tiêu thụ dữ liệu và cách hệ thống phối hợp khi tốc độ phát nhanh hơn tốc độ xử lý. Hiểu rõ các khác biệt này giúp chọn đúng công cụ cho bài toán, thay vì chỉ dựa vào việc API nào có tên `Stream`.

## Bộ sưu tập: nơi lưu dữ liệu

Một collection giữ các phần tử để chương trình có thể truy cập, thêm, xóa, tìm kiếm hoặc duyệt chúng. Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
names.add("An");
names.add("Bình");
names.add("Chi");

for (String name : names) {
    System.out.println(name);
}
```

Sau khi tạo danh sách, các phần tử vẫn được lưu trong `names` cho đến khi bị thay đổi hoặc collection không còn được tham chiếu. Chương trình có thể duyệt danh sách nhiều lần. Khả năng sửa đổi phụ thuộc vào loại collection: `ArrayList` có thể thêm và xóa phần tử, trong khi `List.of(...)` tạo danh sách không sửa đổi được.

Collection thường đại diện cho một tập dữ liệu đã được xác định tại một thời điểm. Nó không tự mô tả cách xử lý bất đồng bộ, lịch phát sự kiện hoặc nhu cầu tiêu thụ. Khi cần duyệt dữ liệu, chương trình có thể dùng vòng lặp hoặc tạo một Java Stream từ collection.

## Java Stream: mô tả phép tính trên một nguồn dữ liệu

Java Stream API cung cấp các thao tác trung gian như `filter`, `map`, `sorted` và các thao tác kết thúc như `collect`, `count`, `reduce`, `forEach`. Các thao tác trung gian thường lazy: chúng xây dựng pipeline nhưng chưa duyệt dữ liệu. Pipeline được thực thi khi có thao tác kết thúc.

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> names = List.of("An", "Bình", "Chi", "Dũng");

List<String> selected = names.stream()
    .filter(name -> name.length() > 2)
    .map(String::toUpperCase)
    .collect(Collectors.toList());

System.out.println(selected);
```

`names.stream()` tạo một Stream mô tả cách duyệt dữ liệu. `filter` và `map` nối các bước xử lý; `collect` kích hoạt việc duyệt và thu kết quả vào một collection mới. Danh sách ban đầu vẫn tồn tại độc lập với danh sách kết quả.

Java Stream không phải cấu trúc lưu trữ. Sau khi một stream đã được tiêu thụ bởi thao tác kết thúc, không thể dùng lại stream đó cho một lần duyệt khác. Muốn xử lý lại dữ liệu, hãy tạo stream mới từ nguồn có thể duyệt lại, chẳng hạn gọi `names.stream()` lần nữa.

Java Stream mặc định xử lý tuần tự trên luồng gọi. Có thể yêu cầu xử lý song song bằng `parallelStream()` hoặc `parallel()`, nhưng điều này chỉ thay đổi cách các phần tử được xử lý. Nó không tạo ra giao thức demand như Reactive Streams và không biến thao tác kết thúc thành một API trả kết quả bất đồng bộ. Thông thường, lời gọi `collect`, `count` hoặc `forEach` vẫn đợi phép tính hoàn tất để trả quyền điều khiển.

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = List.of(12, 80, 120, 240);

List<Integer> largeResults = numbers.parallelStream()
    .filter(number -> number > 100)
    .map(number -> number * number)
    .collect(Collectors.toList());
```

Trong ví dụ, các phần tử có thể được xử lý song song bằng cơ chế thực thi của Java Stream, nhưng luồng gọi vẫn nhận `largeResults` sau khi thao tác kết thúc hoàn tất. Cần chú ý tính an toàn luồng của hàm xử lý, side effect, thứ tự kết quả và chi phí chia nhỏ công việc. Không nên giả định `parallelStream()` luôn nhanh hơn xử lý tuần tự.

## Luồng phản ứng: xử lý dữ liệu và tín hiệu theo nhu cầu

Reactive Streams tập trung vào giao tiếp giữa bên phát và bên nhận. Giao thức chuẩn định nghĩa các vai trò:

- `Publisher<T>` phát các phần tử kiểu `T`.
- `Subscriber<T>` nhận các tín hiệu từ publisher.
- `Subscription` là mối liên kết cho phép subscriber yêu cầu thêm phần tử bằng `request(n)` hoặc hủy bằng `cancel()`.
- `Processor<T, R>` vừa là subscriber của nguồn upstream, vừa là publisher cho downstream; các toán tử trong thư viện reactive thường đóng vai trò xử lý trung gian tương tự.

Trong Reactor, `Flux<T>` biểu diễn từ không đến nhiều phần tử, còn `Mono<T>` biểu diễn từ không đến tối đa một phần tử. Chúng là các kiểu publisher có thể nối với toán tử để tạo thành pipeline:

```java
import reactor.core.publisher.Flux;

Flux<String> names = Flux.just("An", "Bình", "Chi", "Dũng")
    .filter(name -> name.length() > 2)
    .map(String::toUpperCase);

names.subscribe(
    value -> System.out.println("Nhận: " + value),
    error -> System.err.println("Lỗi: " + error.getMessage()),
    () -> System.out.println("Đã hoàn tất")
);
```

Pipeline trên có hình thức xử lý tương tự Java Stream: lọc rồi chuyển đổi từng tên. Tuy nhiên, kết quả được chuyển đến subscriber qua các tín hiệu `onNext`, sau đó là `onComplete` nếu thành công hoặc `onError` nếu thất bại. Subscriber có thể kiểm soát nhu cầu dữ liệu ở mức Reactive Streams. Với publisher đồng bộ như `Flux.just`, các tín hiệu có thể được phát ngay trong quá trình gọi `subscribe`; với nguồn hoặc scheduler bất đồng bộ, tín hiệu có thể đến sau đó trên luồng thực thi khác.

Reactive không có nghĩa là mọi nguồn đều tự động chạy bất đồng bộ. Một pipeline Reactor có thể phát dữ liệu đồng bộ trên luồng gọi. Muốn tạo ranh giới chuyển luồng, cần nguồn bất đồng bộ hoặc cấu hình scheduler phù hợp, ví dụ `subscribeOn` hay `publishOn`. Tương tự, gọi `block()` để lấy kết quả đồng bộ sẽ khiến luồng gọi chờ và làm mất lợi ích không chặn tại điểm đó.

## So sánh trực tiếp

| Khía cạnh | Collection | Java Stream (`java.util.stream`) | Reactive stream (Reactive Streams / Reactor) |
|---|---|---|---|
| Mục đích chính | Lưu và quản lý phần tử | Mô tả phép tính trên nguồn dữ liệu | Phối hợp bên phát và bên nhận dữ liệu theo tín hiệu |
| Dữ liệu | Phần tử được giữ trong cấu trúc | Đọc từ một nguồn; pipeline không lưu kết quả trung gian như collection | Có thể phát dữ liệu theo thời gian, không cần giữ toàn bộ kết quả trong bộ nhớ |
| Kích hoạt | Thao tác thêm, xóa, truy cập hoặc duyệt | Thao tác kết thúc kích hoạt pipeline | `subscribe` thiết lập subscription và khởi động nguồn lazy |
| Tiêu thụ | Truy cập hoặc duyệt bằng iterator/vòng lặp | Thao tác kết thúc như `collect`, `count`, `reduce` | Subscriber nhận `onNext`, `onError`, `onComplete` |
| Điều tiết nhu cầu | Không có giao thức demand chung | Không có `request(n)` theo Reactive Streams | Có `request(n)` và `cancel()` |
| Bất đồng bộ | Không được cung cấp bởi collection | Stream tuần tự mặc định; parallel stream hỗ trợ xử lý song song nhưng thao tác kết thúc thường chờ | Hỗ trợ xử lý bất đồng bộ và ranh giới scheduler; hành vi cụ thể tùy nguồn và pipeline |
| Số lần sử dụng | Có thể duyệt nhiều lần tùy collection | Mỗi Stream chỉ được tiêu thụ một lần | Có thể có nhiều subscription; hành vi chạy lại hay chia sẻ phụ thuộc nguồn cold/hot |
| Dữ liệu vô hạn hoặc kéo dài | Không phù hợp để lưu toàn bộ một luồng vô hạn | Có thể mô tả nguồn vô hạn nhưng thao tác kết thúc phải có điều kiện dừng phù hợp | Phù hợp với luồng sự kiện dài hạn; subscriber có thể giới hạn nhu cầu hoặc hủy |
| Lỗi | Thường xuất hiện trực tiếp từ thao tác hoặc khi duyệt | Ngoại lệ phát sinh trong quá trình thực thi pipeline | Được biểu diễn bằng tín hiệu `onError`, có thể phục hồi bằng toán tử |

Không nên suy ra khả năng chỉ từ tên gọi. Collection có thể được dùng làm nguồn cho cả Java Stream lẫn reactive stream. Java Stream và reactive stream đều có các toán tử như `map` và `filter`, nhưng giao thức tiêu thụ và vòng đời của chúng khác nhau.

## Backpressure: khác biệt quan trọng của Reactive Streams

Java Stream API không định nghĩa cơ chế demand giữa bên xử lý và nguồn dữ liệu. Khi một terminal operation duyệt nguồn, các phần tử được kéo qua pipeline theo cách triển khai của Stream. Có thể dùng `limit` để giới hạn số phần tử được xử lý, nhưng `limit` là một toán tử của pipeline, không phải giao thức để một subscriber báo cho publisher biết mình hiện có thể tiếp nhận bao nhiêu phần tử.

Reactive Streams có cơ chế backpressure. Subscriber gọi `request(n)` để báo số phần tử mà mình sẵn sàng nhận. Publisher phải tôn trọng tổng nhu cầu đã được yêu cầu và không phát `onNext` vượt quá demand. Subscriber cũng có thể gọi `cancel()` để chấm dứt subscription. Các toán tử trung gian có thể điều chỉnh hoặc đệm demand, nên cần chú ý các giới hạn buffer và prefetch khi thiết kế pipeline.

Ví dụ Reactor sau cho thấy subscriber yêu cầu theo từng nhóm nhỏ:

```java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux.range(1, 20).subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(3); // Ban đầu chỉ yêu cầu ba phần tử.
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println("Đã xử lý: " + value);
        request(3); // Yêu cầu thêm sau khi xử lý phần tử hiện tại.
    }
});
```

Đoạn mã minh họa cách điều khiển demand; trong ứng dụng thực tế cần xác định kích thước nhóm và thời điểm yêu cầu dựa trên năng lực xử lý. Với `Long.MAX_VALUE`, subscriber thể hiện nhu cầu không giới hạn. Một yêu cầu không dương vi phạm hợp đồng và dẫn đến lỗi.

Backpressure đặc biệt hữu ích khi nguồn có thể phát nhanh hoặc liên tục, còn bên nhận có năng lực xử lý hữu hạn. Nó giúp phối hợp tốc độ và giới hạn lượng dữ liệu đang chờ xử lý. Backpressure không tự làm cho một hàm chặn trở thành không chặn; thao tác I/O blocking bên trong một toán tử vẫn có thể giữ luồng thực thi.

## Thời gian và dữ liệu đến liên tục

Collection thường biểu diễn các phần tử đã có. Java Stream thường xử lý một lượt dữ liệu từ nguồn, dù nguồn có thể được tạo theo kiểu lazy hoặc vô hạn. Reactive stream phù hợp khi dữ liệu phát sinh theo thời gian: thông báo từ message broker, sự kiện người dùng, thay đổi trạng thái, dữ liệu cảm biến hoặc kết quả từ dịch vụ bất đồng bộ.

Ví dụ, `Flux.interval` phát một số tăng dần theo chu kỳ. Pipeline có thể lấy một số phần tử đầu tiên rồi tiêu thụ:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux.interval(Duration.ofMillis(500))
    .take(3)
    .subscribe(value -> System.out.println("Tick: " + value));
```

Nguồn này phát theo thời gian trên scheduler timer của Reactor. `take(3)` giới hạn số phần tử; sau khi nhận đủ ba phần tử, subscription bị hủy và nguồn dừng phát cho subscriber đó. Đây là cách biểu diễn tự nhiên cho một chuỗi sự kiện có thời điểm phát, trong khi collection không mô tả thời điểm các phần tử xuất hiện.

Java Stream cũng có thể tạo dữ liệu vô hạn bằng `Stream.generate` hoặc `Stream.iterate`, nhưng thao tác kết thúc phải có điều kiện dừng, chẳng hạn `limit`. Stream API không cung cấp hợp đồng subscriber để một bên nhận độc lập điều tiết demand hoặc hủy một nguồn sự kiện đang hoạt động.

## Chuyển đổi giữa collection, Java Stream và reactive stream

Các mô hình có thể kết hợp trong cùng một ứng dụng. Collection thường là nguồn dữ liệu ban đầu; Java Stream thích hợp cho phép tính cục bộ trên tập dữ liệu đã có; reactive stream thích hợp khi cần nối các nguồn bất đồng bộ, xử lý sự kiện hoặc kiểm soát demand.

### Từ collection sang reactive stream

Reactor có thể tạo `Flux` từ một `Iterable`:

```java
List<String> cachedNames = List.of("An", "Bình", "Chi");

Flux<String> names = Flux.fromIterable(cachedNames)
    .filter(name -> name.length() > 2);
```

Việc chuyển đổi này không tự biến collection thành nguồn sự kiện bất đồng bộ. `Flux.fromIterable` thường duyệt collection khi có subscription; nếu không thêm ranh giới scheduler hoặc nguồn bất đồng bộ, việc phát dữ liệu có thể diễn ra đồng bộ trên luồng thực thi subscription.

### Từ Java Stream sang reactive stream

Có thể chuyển Java Stream sang `Flux`, nhưng cần lưu ý Java Stream chỉ được tiêu thụ một lần. Nếu publisher có thể được subscribe nhiều lần, hãy cung cấp một Stream mới cho mỗi lần đăng ký:

```java
List<String> cachedNames = List.of("An", "Bình", "Chi");

Flux<String> names = Flux.fromStream(cachedNames::stream)
    .map(String::toUpperCase);
```

Dạng `Flux.fromStream(cachedNames.stream())` nhận một đối tượng Stream cụ thể, vốn chỉ dùng được một lần. Dùng supplier `cachedNames::stream` giúp Reactor lấy một Stream mới khi cần cho mỗi subscription. Cần bảo đảm nguồn có thể tạo stream mới và có vòng đời tài nguyên phù hợp.

### Thu kết quả reactive về collection

Khi thật sự cần một cấu trúc dữ liệu hoàn chỉnh, có thể thu các phần tử của `Flux` thành `List`:

```java
Mono<List<String>> allNames = Flux.just("An", "Bình", "Chi")
    .map(String::toUpperCase)
    .collectList();
```

`collectList()` tạo `Mono<List<String>>`; danh sách chỉ có khi nguồn hoàn tất. Cách này phù hợp với luồng hữu hạn và kết quả có kích thước có thể kiểm soát. Nếu nguồn kéo dài hoặc vô hạn, việc thu toàn bộ vào một collection sẽ không hoàn tất hoặc có thể tiêu tốn bộ nhớ không giới hạn. Khi đó nên xử lý từng phần tử hoặc theo nhóm thay vì gom toàn bộ.

## Chọn công cụ theo bài toán

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Lưu danh sách đơn hàng để truy cập, cập nhật và duyệt nhiều lần | `List<Order>` hoặc collection phù hợp | Cần cấu trúc lưu trữ và thao tác dữ liệu |
| Lọc, chuyển đổi và tổng hợp một tập dữ liệu hữu hạn trong bộ nhớ | Java Stream | Pipeline gọn, thao tác kết thúc tạo kết quả đồng bộ |
| Xử lý phép tính CPU song song trên tập dữ liệu hữu hạn | Java parallel Stream hoặc executor phù hợp | Có thể chia nhỏ công việc; cần đo hiệu năng và kiểm soát side effect |
| Kết hợp nhiều lời gọi I/O bất đồng bộ | `Mono` / `Flux` và client reactive | Có thể nối kết quả bất đồng bộ mà không phải chờ đồng bộ ở từng bước |
| Tiếp nhận sự kiện liên tục với tốc độ phát và nhận khác nhau | Reactive Streams | Có demand, hủy subscription và tín hiệu kết thúc |
| Cần cả dữ liệu lưu trữ lẫn xử lý reactive | Collection kết hợp `Flux.fromIterable` hoặc repository reactive | Mỗi thành phần đảm nhiệm đúng vai trò trong kiến trúc |

Khi chọn reactive stream, cần kiểm tra toàn bộ chuỗi từ nguồn đến subscriber. Một pipeline trả về `Flux` nhưng bên trong gọi JDBC đồng bộ hoặc `block()` vẫn có thể chiếm luồng trong thời gian chờ. Scheduler có thể cô lập một số tác vụ blocking, nhưng không thay đổi bản chất của API nguồn. Ưu tiên driver và client hỗ trợ I/O không chặn khi cần khả năng phục vụ đồng thời cao.

## Những nhầm lẫn cần tránh

- **Collection và Stream là một:** collection lưu phần tử; Java Stream mô tả phép tính duyệt nguồn. Stream không phải bản sao collection và không lưu kết quả trung gian như một danh sách.
- **Java Stream và reactive stream giống nhau vì cùng có `map` và `filter`:** tên toán tử tương tự, nhưng cơ chế kích hoạt, giao thức tiêu thụ, demand và vòng đời khác nhau.
- **Parallel Stream là reactive:** xử lý song song không đồng nghĩa với giao thức bất đồng bộ có backpressure. Terminal operation của parallel Stream vẫn thường trả kết quả sau khi phép tính hoàn tất.
- **Reactive luôn chạy trên luồng khác:** nguồn reactive có thể phát đồng bộ. Cần xem nguồn và scheduler để xác định nơi thực thi.
- **Chuyển collection thành `Flux` là đã có backpressure cho mọi tầng:** publisher tuân thủ demand ở giao thức, nhưng các toán tử có thể đệm hoặc prefetch. Cần cấu hình và quan sát các giới hạn của pipeline.
- **Có thể thu mọi `Flux` thành `List`:** chỉ nên thu toàn bộ khi nguồn hữu hạn và kích thước kết quả được kiểm soát.

Khi thiết kế ứng dụng Java, hãy bắt đầu từ bản chất dữ liệu và cách nó được tiêu thụ. Dùng collection để lưu giữ dữ liệu, Java Stream để mô tả phép tính trên nguồn hữu hạn, và reactive stream khi cần phối hợp tín hiệu theo thời gian, xử lý bất đồng bộ hoặc điều tiết nhu cầu giữa bên phát và bên nhận. Việc phân biệt đúng ba vai trò này giúp pipeline rõ ràng, kiểm soát tài nguyên tốt hơn và tránh vô tình đưa điểm chặn vào luồng xử lý reactive.
