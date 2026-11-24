# Cửa sổ chồng lấn, khoảng trống và điều kiện đóng cửa sổ

Trong một luồng sự kiện, đôi khi cần chia dữ liệu thành những nhóm liên tiếp để xử lý theo lô, tính thống kê hoặc phát hiện mẫu. Một cửa sổ (*window*) là một publisher con chứa một đoạn phần tử của luồng nguồn. Khác với `buffer`, vốn thu thập phần tử thành một collection rồi phát collection đó, `window` phát ra các publisher con để downstream có thể xử lý dữ liệu trong từng cửa sổ theo kiểu reactive.

Khi tạo cửa sổ, cần xác định hai điều: cửa sổ mới bắt đầu khi nào và cửa sổ hiện tại đóng khi nào. Nếu cửa sổ mới bắt đầu trước khi cửa sổ cũ đóng, các cửa sổ chồng lấn và một phần tử có thể xuất hiện trong nhiều cửa sổ. Nếu cửa sổ mới chỉ bắt đầu sau khi cửa sổ cũ đã kết thúc một khoảng, giữa chúng có khoảng trống và một số phần tử không thuộc cửa sổ nào. Reactor hỗ trợ các quy tắc này bằng những toán tử `window` theo kích thước, thời gian, predicate hoặc publisher ranh giới.

## 1. Window tạo Flux lồng nhau

Với nguồn `Flux<T>`, toán tử `window` trả về một `Flux<Flux<T>>`: publisher ngoài phát các publisher con, mỗi publisher con đại diện cho một cửa sổ:

```java
Flux<Flux<Integer>> windows = Flux.range(1, 10)
    .window(3);
```

`window(3)` chia luồng thành các cửa sổ tối đa ba phần tử. Có thể xử lý từng cửa sổ bằng cách nối một toán tử vào publisher con:

```java
Flux<List<Integer>> batches = Flux.range(1, 10)
    .window(3)
    .concatMap(window -> window.collectList());
```

Kết quả là các danh sách `[1, 2, 3]`, `[4, 5, 6]`, `[7, 8, 9]` và `[10]`. Cửa sổ cuối cùng vẫn được phát dù chưa đủ ba phần tử vì nguồn đã hoàn tất.

`window` phù hợp khi muốn xử lý phần tử theo luồng bên trong từng nhóm, ví dụ đếm số sự kiện, gọi một dịch vụ theo từng nhóm hoặc kết hợp dữ liệu theo cửa sổ. Nếu chỉ cần một `List<T>` sau khi thu thập xong, `buffer` có thể đơn giản hơn. Với `window`, mỗi cửa sổ là một publisher nên có thể tiếp tục dùng các toán tử reactive và quản lý backpressure cho phần tử trong cửa sổ.

## 2. Kích thước và bước trượt xác định overlap hoặc gap

Reactor có overload `window(maxSize, skip)`. `maxSize` là số phần tử tối đa trong mỗi cửa sổ; `skip` là số phần tử nguồn giữa hai lần mở cửa sổ liên tiếp. Hai giá trị này quyết định quan hệ giữa các cửa sổ:

- `skip == maxSize`: các cửa sổ liền nhau, không chồng lấn và không có khoảng trống.
- `skip < maxSize`: cửa sổ mới mở trước khi cửa sổ trước đóng, tạo vùng chồng lấn.
- `skip > maxSize`: cửa sổ trước đóng trước khi cửa sổ tiếp theo mở, tạo khoảng trống.

| Cấu hình | Hành vi | Hệ quả |
| --- | --- | --- |
| `window(3, 3)` | Mỗi ba phần tử mở một cửa sổ mới | Các cửa sổ liền nhau |
| `window(3, 2)` | Mỗi hai phần tử mở cửa sổ mới, mỗi cửa sổ nhận tối đa ba phần tử | Chồng lấn một phần tử |
| `window(2, 4)` | Mỗi bốn phần tử mở cửa sổ mới, mỗi cửa sổ nhận tối đa hai phần tử | Bỏ qua hai phần tử giữa các cửa sổ |

### Cửa sổ liền nhau

```java
Flux.range(1, 8)
    .window(3, 3)
    .concatMap(window -> window.collectList());
```

```text
Nguồn:       1  2  3  4  5  6  7  8
Cửa sổ 1:   [1  2  3]
Cửa sổ 2:             [4  5  6]
Cửa sổ 3:                       [7  8]
```

Mỗi phần tử thuộc đúng một cửa sổ. Cửa sổ cuối cùng có hai phần tử vì nguồn kết thúc trước khi đủ ba.

### Cửa sổ chồng lấn

Khi `maxSize` lớn hơn `skip`, một phần tử có thể thuộc nhiều cửa sổ:

```java
Flux.range(1, 8)
    .window(3, 2)
    .concatMap(window -> window.collectList());
```

```text
Nguồn:       1  2  3  4  5  6  7  8
Cửa sổ 1:   [1  2  3]
Cửa sổ 2:         [3  4  5]
Cửa sổ 3:               [5  6  7]
Cửa sổ 4:                     [7  8]
```

Ở đây, cửa sổ mới bắt đầu sau mỗi hai phần tử nguồn, trong khi mỗi cửa sổ chứa tối đa ba phần tử. Giá trị `3`, `5` và `7` xuất hiện trong hai cửa sổ. Đây là hành vi có chủ đích, hữu ích khi cần tính toán trên các đoạn dữ liệu liên tiếp có vùng giao nhau, chẳng hạn trung bình trượt theo nhóm ba mẫu.

### Cửa sổ có khoảng trống

Khi `skip` lớn hơn `maxSize`, một số phần tử nằm ngoài mọi cửa sổ:

```java
Flux.range(1, 10)
    .window(2, 4)
    .concatMap(window -> window.collectList());
```

```text
Nguồn:       1  2  3  4  5  6  7  8  9  10
Cửa sổ 1:   [1  2]
Khoảng trống:      3  4
Cửa sổ 2:                     [5  6]
Khoảng trống:                        7  8
Cửa sổ 3:                                       [9  10]
```

Các phần tử `3`, `4`, `7` và `8` không được đưa vào cửa sổ nào. Cách này hữu ích khi chỉ cần lấy một đoạn dữ liệu định kỳ và cố ý bỏ phần ở giữa. Nếu nghiệp vụ yêu cầu không mất bất kỳ phần tử nào, hãy chọn `skip <= maxSize` hoặc một chiến lược phân nhóm khác.

## 3. Cửa sổ theo thời gian

Khi ranh giới nhóm được xác định bởi thời gian thay vì số phần tử, có thể dùng các overload theo `Duration`:

```java
Flux<Flux<Event>> perMinute = eventStream
    .window(Duration.ofMinutes(1));
```

`window(Duration)` mở các cửa sổ thời gian liên tiếp có cùng độ dài. Một cửa sổ đóng khi hết khoảng thời gian; cửa sổ tiếp theo được mở cho khoảng kế tiếp. Tốc độ phát của nguồn không quyết định kích thước cửa sổ: một cửa sổ có thể chứa nhiều, ít hoặc không có sự kiện.

Overload nhận cả độ dài và chu kỳ mở cửa sổ cho phép tạo overlap hoặc gap theo thời gian:

```java
// Cửa sổ dài 10 giây, mở cửa sổ mới mỗi 5 giây: overlap 5 giây.
Flux<Flux<Metric>> overlapping = metrics.window(
    Duration.ofSeconds(10),
    Duration.ofSeconds(5)
);

// Cửa sổ dài 5 giây, mở cửa sổ mới mỗi 10 giây: gap 5 giây.
Flux<Flux<Metric>> gapped = metrics.window(
    Duration.ofSeconds(5),
    Duration.ofSeconds(10)
);
```

Trong ví dụ đầu, cửa sổ thứ hai bắt đầu trước khi cửa sổ thứ nhất đóng nên các sự kiện trong vùng giao nhau có thể xuất hiện ở cả hai cửa sổ. Trong ví dụ thứ hai, giữa lúc một cửa sổ đóng và cửa sổ tiếp theo mở có khoảng thời gian không thuộc cửa sổ nào; sự kiện đến trong khoảng đó không được gom vào cửa sổ.

| Độ dài cửa sổ | Chu kỳ mở | Quan hệ |
| --- | --- | --- |
| 10 giây | 10 giây | Liền nhau |
| 10 giây | 5 giây | Chồng lấn 5 giây |
| 5 giây | 10 giây | Khoảng trống 5 giây |

Các cửa sổ thời gian được điều phối bởi scheduler. Nếu cần kiểm thử chính xác, dùng scheduler ảo và `StepVerifier.withVirtualTime`; không dựa vào `Thread.sleep` dài để chờ cửa sổ đóng.

## 4. Đóng cửa sổ khi đạt kích thước hoặc hết thời gian

Trong nhiều hệ thống, một batch cần được phát khi đủ số phần tử, nhưng cũng không nên chờ vô hạn nếu tốc độ dữ liệu thấp. `windowTimeout(maxSize, maxTime)` đóng cửa sổ khi đạt một trong hai điều kiện: đủ `maxSize` phần tử hoặc hết `maxTime`:

```java
Flux<List<Event>> batches = eventStream
    .windowTimeout(100, Duration.ofSeconds(2))
    .concatMap(window -> window.collectList());
```

Nếu có 100 sự kiện đến trước hai giây, cửa sổ đóng vì đạt kích thước. Nếu chỉ có 12 sự kiện trong hai giây, cửa sổ đóng theo thời gian và nhóm 12 sự kiện được xử lý. Cơ chế này cân bằng giữa hiệu quả batch và độ trễ chờ dữ liệu.

```text
Điều kiện kích thước:
Sự kiện:       ● ● ● ● ● ● ● ●
Giới hạn:      4 phần tử
Cửa sổ:       [● ● ● ●] [● ● ● ●]
Đóng:          size       size

Điều kiện thời gian:
Sự kiện:       ● ● ●       ●
Thời gian:     |-----------2 giây-----------|
Cửa sổ:       [● ● ●       ●]
Đóng:                                  timeout
```

Trong ứng dụng thực tế, cần chọn `maxSize` và `maxTime` theo giới hạn payload, chi phí xử lý và độ trễ đầu ra. Kích thước quá lớn làm batch giữ nhiều dữ liệu; thời gian quá dài khiến sự kiện phải chờ lâu; thời gian quá ngắn có thể tạo nhiều batch nhỏ.

## 5. Đóng cửa sổ theo điều kiện của phần tử

Không phải lúc nào ranh giới cửa sổ cũng là số lượng hoặc thời gian. Một luồng có thể chứa sự kiện đánh dấu kết thúc nhóm, chẳng hạn `END_OF_TRANSACTION`, `END_OF_MESSAGE` hoặc một dòng phân cách. `windowUntil(predicate)` đóng cửa sổ khi predicate khớp:

```java
Flux<Flux<String>> messages = lines.windowUntil(
    line -> line.equals("END")
);
```

Với mặc định `cutBefore = false`, phần tử làm predicate đúng được đưa vào cửa sổ hiện tại rồi cửa sổ đóng. Ví dụ:

```text
Nguồn:              A  B  END  C  D  END  E
windowUntil:       [A  B  END] [C  D  END] [E]
```

Nếu muốn phần tử ranh giới bắt đầu cửa sổ tiếp theo, dùng overload `windowUntil(predicate, true)`:

```java
Flux<Flux<String>> messages = lines.windowUntil(
    line -> line.equals("END"),
    true
);
```

Khi đó, phần tử khớp predicate được cắt sang đầu cửa sổ kế tiếp:

```text
Nguồn:                    A  B  END  C  D  END  E
windowUntil(cutBefore):  [A  B] [END  C  D] [END  E]
```

Hãy chọn cách đặt phần tử ranh giới theo định dạng dữ liệu. Nếu `END` là phần kết thúc của bản ghi, mặc định thường phù hợp. Nếu nó là dấu mở đầu của bản ghi tiếp theo, `cutBefore = true` có thể diễn đạt đúng hơn.

`windowWhile(predicate)` có ý nghĩa khác: nó giữ các phần tử liên tiếp thỏa predicate trong một cửa sổ và đóng cửa sổ khi gặp phần tử không thỏa. Phần tử không thỏa predicate bị loại khỏi các cửa sổ:

```java
Flux<Flux<Integer>> positiveRuns = values.windowWhile(value -> value > 0);
```

```text
Nguồn:              1  2  0  3  4  0  5
windowWhile(> 0):   [1  2]    [3  4]    [5]
Phần tử bị loại:          0          0
```

`windowUntil` và `windowWhile` phù hợp khi dữ liệu có ranh giới dựa trên nội dung. Cần nhớ rằng `windowWhile` không phát các phần tử phân cách; nếu các phần tử đó cũng cần được xử lý, hãy tách hoặc lưu chúng bằng một nhánh khác trước khi áp dụng.

## 6. Đóng cửa sổ bằng publisher ranh giới

Với ranh giới động, có thể mở cửa sổ theo một publisher và đóng từng cửa sổ bằng publisher khác. `windowWhen` nhận một publisher phát tín hiệu mở cửa sổ và một hàm tạo publisher đóng tương ứng:

```java
Flux<Flux<Event>> sessions = eventStream.windowWhen(
    sessionStarts,
    start -> sessionEndsFor(start)
);
```

Mỗi tín hiệu từ `sessionStarts` mở một cửa sổ. Publisher được trả về từ `sessionEndsFor` quyết định khi nào cửa sổ đó đóng. Cách này hữu ích cho phiên người dùng, khoảng thời gian giao dịch hoặc nhóm sự kiện có ranh giới do một luồng điều khiển riêng phát ra.

Vì các cửa sổ có thể tồn tại đồng thời, cần xác định rõ sự kiện nào thuộc cửa sổ nào và có thể thuộc nhiều cửa sổ hay không. Nếu publisher mở cửa sổ phát nhanh hơn publisher đóng, số cửa sổ đang hoạt động có thể tăng. Hãy thiết kế giới hạn và chính sách kết thúc phù hợp, tránh để cửa sổ mở vô hạn khi tín hiệu đóng không bao giờ đến.

## 7. Nguồn hoàn tất, lỗi hoặc bị hủy khi cửa sổ đang mở

Vòng đời của nguồn ảnh hưởng đến tất cả cửa sổ đang hoạt động:

- **Nguồn hoàn tất:** các cửa sổ còn mở được kết thúc; cửa sổ cuối có thể chứa ít phần tử hơn giới hạn.
- **Nguồn phát lỗi:** lỗi được chuyển tới các publisher cửa sổ đang hoạt động và luồng ngoài kết thúc bằng lỗi.
- **Downstream hủy:** subscription tới nguồn được hủy theo chuỗi; các cửa sổ không còn được tiêu thụ cũng kết thúc theo vòng đời hủy.
- **Ranh giới không đến:** với cửa sổ đóng bằng predicate hoặc publisher điều khiển, cần xác định timeout hoặc điều kiện thay thế nếu cửa sổ có thể mở quá lâu.

Không nên xem việc đóng cửa sổ do đạt size, timer hoặc predicate là cùng một loại sự kiện nghiệp vụ. Nếu downstream cần biết vì sao batch được phát, hãy mang metadata về nguyên nhân đóng vào kết quả xử lý, hoặc dùng một cấu trúc miền nghiệp vụ biểu diễn rõ batch và trạng thái đóng.

## 8. Xử lý từng cửa sổ và quản lý thứ tự

Publisher ngoài phát các cửa sổ theo thứ tự chúng được mở. Có thể dùng `concatMap` để xử lý từng cửa sổ theo thứ tự và chờ xử lý cửa sổ trước hoàn tất:

```java
Flux<BatchResult> results = eventStream
    .window(100, 80)
    .concatMap(window -> window
        .collectList()
        .flatMap(batchService::process));
```

Vì `maxSize` là 100 và `skip` là 80, các cửa sổ chồng lấn 20 phần tử. `concatMap` giữ thứ tự xử lý cửa sổ, phù hợp khi batch sau phụ thuộc kết quả batch trước. Nếu các batch độc lập và có thể xử lý đồng thời, có thể dùng `flatMap` với concurrency giới hạn:

```java
Flux<BatchResult> results = eventStream
    .window(100)
    .flatMap(window -> window
        .collectList()
        .flatMap(batchService::process),
        4
    );
```

Trong trường hợp này, tối đa bốn thao tác xử lý batch có thể hoạt động đồng thời; thứ tự hoàn tất kết quả không nhất thiết giữ thứ tự cửa sổ ban đầu. Nếu cần concurrency nhưng vẫn giữ thứ tự đầu ra, có thể cân nhắc `flatMapSequential`, đồng thời lưu ý các kết quả hoàn tất sớm có thể phải chờ trong bộ đệm.

Với cửa sổ chồng lấn, cùng một phần tử có thể được xử lý nhiều lần trong các batch khác nhau. Nếu xử lý có tác dụng phụ như ghi database hoặc gửi lệnh, hãy đảm bảo thao tác idempotent hoặc thiết kế khóa chống trùng phù hợp. Với cửa sổ có khoảng trống, các phần tử ngoài cửa sổ sẽ không tới bước xử lý batch; hãy xác nhận việc bỏ chúng là yêu cầu nghiệp vụ.

## 9. Window và buffer khác nhau ở cách biểu diễn nhóm

| Khía cạnh | `window` | `buffer` |
| --- | --- | --- |
| Kết quả | Publisher con, ví dụ `Flux<Flux<T>>` | Collection, ví dụ `Flux<List<T>>` |
| Xử lý | Có thể xử lý từng phần tử khi nó đi vào cửa sổ | Thường phát collection sau khi buffer đóng |
| Compose | Dùng toán tử reactive trên từng cửa sổ | Dùng toán tử trên collection đã thu thập |
| Tài nguyên | Có thể giữ publisher con và dữ liệu đang chờ subscriber | Giữ các phần tử trong collection tới khi phát buffer |
| Trường hợp phù hợp | Nhóm dữ liệu cần xử lý reactive theo luồng | Nhóm dữ liệu cần một collection hoàn chỉnh |

Ví dụ `buffer(3, 2)` tạo các danh sách chồng lấn; `window(3, 2)` tạo các publisher chồng lấn. Cả hai dùng cùng nguyên tắc kích thước và bước trượt, nhưng cách downstream tiêu thụ dữ liệu khác nhau.

## 10. Backpressure và tài nguyên của cửa sổ

Windowing tạo hai cấp subscription: subscriber nhận các cửa sổ từ publisher ngoài, rồi subscriber đó hoặc toán tử tiếp theo đăng ký vào từng publisher con để nhận phần tử. Vì vậy, cần tiêu thụ các cửa sổ đã phát và tránh để publisher con không được subscribe hoặc xử lý quá chậm trong khi nguồn tiếp tục phát.

Một cửa sổ chồng lấn làm một phần tử có thể được chuyển tới nhiều publisher con. Điều này làm tăng tổng công việc downstream và có thể làm tăng dữ liệu được giữ trong bộ nhớ. `flatMap` không giới hạn concurrency có thể mở nhiều thao tác xử lý batch cùng lúc; hãy đặt concurrency, prefetch và giới hạn buffer phù hợp với tốc độ nguồn.

Nếu một cửa sổ có thể tồn tại rất lâu, hãy đặt điều kiện đóng rõ ràng bằng size, thời gian hoặc publisher ranh giới. Nếu downstream cần gom cửa sổ thành collection, `collectList()` chỉ nên dùng khi kích thước cửa sổ có giới hạn hợp lý. Tránh thu thập một cửa sổ không giới hạn thành một danh sách lớn trong bộ nhớ.

## 11. Kiểm thử overlap, gap và điều kiện đóng

Có thể dùng `StepVerifier` để xác minh chính xác các phần tử thuộc từng cửa sổ:

```java
StepVerifier.create(
        Flux.range(1, 8)
            .window(3, 2)
            .concatMap(window -> window.collectList())
    )
    .expectNext(List.of(1, 2, 3))
    .expectNext(List.of(3, 4, 5))
    .expectNext(List.of(5, 6, 7))
    .expectNext(List.of(7, 8))
    .verifyComplete();
```

Kiểm thử khoảng trống:

```java
StepVerifier.create(
        Flux.range(1, 10)
            .window(2, 4)
            .concatMap(window -> window.collectList())
    )
    .expectNext(List.of(1, 2))
    .expectNext(List.of(5, 6))
    .expectNext(List.of(9, 10))
    .verifyComplete();
```

Với cửa sổ thời gian hoặc `windowTimeout`, dùng `StepVerifier.withVirtualTime` để tiến thời gian và xác minh cửa sổ đóng đúng khi đạt size hoặc timeout. Với `windowUntil`, kiểm tra riêng cả hai giá trị `cutBefore`; với `windowWhile`, xác minh phần tử không khớp predicate có bị loại đúng như mong muốn. Nên có test cho nguồn hoàn tất khi cửa sổ chưa đủ size, nguồn lỗi khi cửa sổ còn mở và downstream hủy giữa chừng.

## 12. Chọn cách mở và đóng cửa sổ theo ý nghĩa dữ liệu

Hãy bắt đầu từ câu hỏi nghiệp vụ: một nhóm cần bao nhiêu phần tử, mở nhóm mới theo số phần tử hay theo thời gian, và điều kiện nào xác định nhóm đã hoàn tất? Dùng `window(maxSize, skip)` khi kích thước và bước trượt được xác định theo số phần tử. Dùng `window(Duration)` hoặc overload có chu kỳ mở riêng khi ranh giới dựa trên thời gian. Dùng `windowTimeout` khi cần đóng theo size hoặc thời gian, tùy điều kiện nào đến trước. Dùng `windowUntil`, `windowWhile` hoặc `windowWhen` khi ranh giới phụ thuộc nội dung hay một publisher điều khiển.

Chồng lấn có nghĩa một phần tử thuộc nhiều cửa sổ; khoảng trống có nghĩa một số phần tử không thuộc cửa sổ nào. Đây là lựa chọn về hợp đồng dữ liệu, không chỉ là chi tiết hiệu năng. Khi đã chọn, hãy kiểm thử thành viên của từng cửa sổ, thứ tự xử lý, điều kiện đóng và hành vi khi nguồn complete/error/cancel. Nhờ đó, việc gom và chia luồng trong Reactor có thể đáp ứng đúng yêu cầu xử lý batch mà vẫn giữ được khả năng compose và điều tiết của Reactive Streams.
