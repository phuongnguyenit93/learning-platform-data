# Phân biệt nguồn gốc Java 5 với API được bổ sung ở phiên bản sau

## 1. Vì sao cần phân biệt nguồn gốc?

Một ví dụ học generics có thể viết:

```java
List<String> names = List.of("An", "Binh");
```

Dòng này kết hợp hai phần thuộc hai mốc:

- `List<String>` dùng tham số kiểu, một nền tảng ngôn ngữ từ Java 5.
- `List.of(...)` là phương thức tạo danh sách được bổ sung ở Java 9.

Vì vậy, “ví dụ giải thích tính năng Java 5” không có nghĩa “toàn bộ mã trong ví dụ chỉ dùng API có từ Java 5”.

Phân biệt nguồn gốc giúp:

1. Giải thích đúng phần kiến thức đang học.
2. Chọn mức Java đích phù hợp khi biên dịch.
3. Đọc chính xác tài liệu và ví dụ.
4. Tránh nhầm phiên bản của một lớp với phiên bản của từng phương thức.
5. Dùng tiện ích hiện đại mà vẫn hiểu nền tảng chúng dựa trên.

Bài chỉ dùng các cơ chế và API còn áp dụng trong Java hiện đại. Không cần cài môi trường Java 5 hay viết lại chương trình theo phong cách cũ để chứng minh nguồn gốc của một tính năng.

## 2. Có ít nhất ba loại mốc khác nhau

### 2.1. Mốc của cơ chế ngôn ngữ

Ví dụ:

- Generics: cách khai báo và sử dụng tham số kiểu.
- Enum: khai báo một kiểu có tập hằng xác định.
- Enhanced for: vòng lặp duyệt từng phần tử.
- Autoboxing/unboxing: chuyển đổi giữa kiểu nguyên thủy và wrapper theo ngữ cảnh.
- Varargs: tham số nhận số đối số thay đổi.
- Static import: sử dụng thành viên tĩnh mà không luôn ghi tên lớp.

Bản tổng hợp [cải tiến ngôn ngữ của Oracle](https://docs.oracle.com/javase/8/docs/technotes/guides/language/enhancements.html) đặt các cơ chế trên ở Java 5; nó cũng phân biệt diamond ở Java 7 và lambda/method reference ở Java 8.

Cú pháp `new ArrayList<>()` có dấu `<>` suy luận ở vị trí tạo đối tượng, nhưng điều đó không làm generics trở thành tính năng chỉ có từ Java 7. Cơ chế gốc và tiện ích suy luận được mở rộng có mốc khác nhau.

### 2.2. Mốc của lớp hoặc giao diện

Một lớp/giao diện có thể đã tồn tại từ lâu, sau đó mới được mở rộng.

Ví dụ `List` không phải được tạo ra lần đầu cùng generics. Bộ thư viện được tham số hóa để phối hợp với cơ chế kiểu mới. Khi xem `Since` ở đầu trang `List`, không được dùng riêng mốc đó để định tuổi cho toàn bộ các cách sử dụng hiện tại.

Tương tự, `String` đã tồn tại rất lâu nhưng không phải mọi phương thức hiện nay của `String` đều có từ đầu.

### 2.3. Mốc của một thành viên cụ thể

Một API có thể thêm phương thức ở phiên bản sau:

| Kiểu chứa | Thành viên cần hỏi | Mốc |
| --- | --- | --- |
| `List` | `of(...)` | Java 9 |
| `List` | `copyOf(...)` | Java 10 |
| `Optional` | `isEmpty()` | Java 11 |
| `String` | `repeat(int)` | Java 11 |
| `Stream` | `toList()` | Java 16 |

Để biết một lời gọi có sử dụng được ở mức Java đích hay không, phải xem đúng thành viên và đúng chữ ký. Chỉ nhìn tên package hoặc dòng `Since` đầu trang chưa đủ.

## 3. Cách đọc Since trong tài liệu API

Khi cần kiểm tra một lời gọi:

1. Xác định tên đầy đủ của kiểu, chẳng hạn `java.util.stream.Stream`.
2. Tới tài liệu của đúng kiểu.
3. Mở phần chi tiết đúng phương thức, không chỉ xem bảng tóm tắt.
4. Kiểm tra `Since` của thành viên.
5. Đọc hợp đồng và các ghi chú liên quan.

Ví dụ, [List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html) ghi `Since: 9` cho các factory `of` và `Since: 10` cho `copyOf`. Không thể kết luận cả hai có cùng mốc chỉ vì chúng đều tạo danh sách không cho sửa cấu trúc.

[Optional](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Optional.html) có mốc lớp là `1.8`, còn `isEmpty()` ghi `Since: 11`. Mốc `1.8` ở đây tương ứng Java 8, không phải một phiên bản Java riêng có tên “1 chấm 8” khác bản Java 8.

Một thành viên không ghi `Since` riêng không có nghĩa là mới nhất. Cần đọc ngữ cảnh tài liệu và mốc của kiểu; khi vẫn chưa chắc, đối chiếu tài liệu phiên bản hoặc ghi chú phát hành chính thức.

Nếu có nhiều overload, phải xem đúng overload đang gọi. Một phương thức cùng tên có thể có các dạng được bổ sung ở các phiên bản khác nhau.

## 4. Những tổ hợp thường gặp trong mã hiện đại

### 4.1. Generics và diamond

```java
List<String> names = new ArrayList<>();
```

Phân tích:

| Phần | Ý nghĩa | Nguồn gốc |
| --- | --- | --- |
| `List<String>` | Danh sách dùng với phần tử `String` | Generics từ Java 5 |
| `new ArrayList<>()` | Suy luận đối số kiểu khi tạo đối tượng | Diamond từ Java 7 |
| Kiểu `List`/`ArrayList` | Thư viện tập hợp | Có lịch sử riêng, không đồng nhất với mốc diamond |

Viết ví dụ này trong bài generics hiện đại là phù hợp nếu giải thích đúng các lớp. Không cần làm mã dài hơn chỉ để nó trông giống một thời kỳ cũ.

### 4.2. Generics và factory danh sách

```java
List<String> names = List.of("An", "Binh");
List<String> snapshot = List.copyOf(names);
```

Generics diễn tả kiểu phần tử. Hai phương thức `of` và `copyOf` là API thư viện bổ sung ở Java 9 và Java 10.

Ngoài mốc, còn phải hiểu hợp đồng: các danh sách này không cho thêm, xóa hoặc thay phần tử và không chấp nhận phần tử `null`. Phần tử nếu là đối tượng có thể thay đổi thì bản thân đối tượng đó không tự trở nên bất biến.

Nguồn gốc API không thay thế việc đọc hợp đồng dữ liệu.

### 4.3. Enhanced for và Stream là hai cơ chế khác nhau

```java
for (String name : names) {
    System.out.println(name);
}
```

là vòng lặp mở rộng. Còn:

```java
names.stream().filter(name -> name.length() > 2).count();
```

kết hợp API Stream và lambda, thuộc bước phát triển Java 8.

Hai đoạn có thể cùng xuất hiện trong một tệp hiện đại. Việc chúng cùng xử lý danh sách không làm chúng có cùng nguồn gốc.

Cũng không nên gọi `Stream.forEach` là chính vòng lặp enhanced for chỉ vì cả hai đều “duyệt phần tử”. Một cái là cú pháp của ngôn ngữ; cái còn lại là lời gọi API nhận hành vi.

### 4.4. Stream và phương thức kết thúc được bổ sung sau

`Stream` có từ Java 8, nhưng [Stream.toList()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html#toList()) được bổ sung ở Java 16.

```java
List<String> selected = names.stream()
        .filter(name -> name.length() > 2)
        .toList();
```

Phần pipeline phía trước có thể dùng những cơ chế Java 8; phương thức kết thúc phía sau nâng yêu cầu API của toàn đoạn lên ít nhất mức có `toList`.

Không suy rằng mọi phương thức xuất hiện trên `Stream` trong tài liệu JDK hiện tại đều dùng được trên Java 8.

### 4.5. Annotation và annotation cụ thể

Nền tảng annotation có từ Java 5, nhưng một annotation cụ thể hoặc vị trí sử dụng mở rộng có thể ra đời sau.

Ví dụ `@FunctionalInterface` gắn với mô hình giao diện hàm được bổ sung ở Java 8. Không nên nói “mọi annotation đều có từ Java 5” chỉ vì cú pháp `@...` là quen thuộc.

Cần hỏi riêng:

- Cơ chế annotation xuất hiện khi nào?
- Annotation đang dùng thuộc JDK hay thư viện ngoài?
- Nó được bổ sung ở phiên bản nào?
- Bên nào diễn giải nó?

Một annotation của một framework không được xác định phiên bản bằng số phiên bản Java. Nó còn có vòng đời của thư viện cung cấp annotation đó.

## 5. Một bảng phân loại gọn để tra cứu

| Thành phần | Mốc hoặc lớp nguồn gốc cần nhớ | Quan hệ với nền tảng Java 5 |
| --- | --- | --- |
| Tham số kiểu `<T>` | Java 5 | Trực tiếp |
| Enum, enhanced for, boxing, varargs, static import | Java 5 | Trực tiếp |
| Cơ chế annotation | Java 5 | Trực tiếp, còn có mở rộng về sau |
| `Callable<V>`, `Future<V>`, `ExecutorService` | Java 5 | API đồng thời có kiểu |
| Diamond `<>` khi tạo đối tượng | Java 7 | Tiện ích suy luận cho kiểu tổng quát |
| Lambda và method reference | Java 8 | Cách biểu đạt hành vi bổ sung sau |
| `Stream`, `Optional`, `java.time` | Java 8 | API mới dùng cùng nhiều nền tảng kiểu trước đó |
| `List.of` | Java 9 | Factory bổ sung trên giao diện đã tồn tại |
| `List.copyOf` | Java 10 | Thành viên mới, không đồng mốc với `of` |
| `String.repeat`, `Optional.isEmpty` | Java 11 | Phương thức bổ sung trên kiểu có trước |
| `Stream.toList` | Java 16 | Phương thức kết thúc bổ sung sau Stream |
| `Executors.newVirtualThreadPerTaskExecutor` | Java 21 | Cơ chế thực thi mới trên lớp tiện ích có từ trước |

Bảng tập trung vào những ví dụ còn dùng được. Nó không phải danh sách toàn bộ thay đổi của từng bản Java.

Ví dụ cuối đặc biệt hữu ích: [Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html#newVirtualThreadPerTaskExecutor()) có phương thức tạo executor cho virtual thread từ Java 21. Mốc của lớp `Executors` không thể dùng để tuyên bố phương thức đó có từ Java 5.

Một API mới cũng không tự động thay mọi lựa chọn cũ còn phù hợp. Cần đọc yêu cầu và hợp đồng, chẳng hạn tải công việc, tác vụ chặn hay CPU, giới hạn tài nguyên và vòng đời.

## 6. Chương trình Java 17+ kết hợp nhiều mốc

Lưu thành `FeatureOriginDemo.java`:

```java
import java.util.List;
import java.util.Optional;

public class FeatureOriginDemo {
    enum Origin {
        JAVA_5_FOUNDATION,
        LATER_ADDITION
    }

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }
        return values.get(0);
    }

    public static void main(String[] args) {
        List<String> topics = List.of("generics", "enum", "annotations");

        List<String> selected = topics.stream()
                .filter(topic -> topic.length() >= 7)
                .toList();

        Optional<String> firstSelected = selected.stream().findFirst();

        System.out.println("foundation = " + Origin.JAVA_5_FOUNDATION);
        System.out.println("all topics = " + topics);
        System.out.println("selected = " + selected);
        System.out.println("generic first = " + first(selected));
        System.out.println("optional empty = " + firstSelected.isEmpty());
        System.out.println("separator = " + "=".repeat(8));

        for (String topic : selected) {
            System.out.println("topic = " + topic);
        }

        try {
            selected.add("another");
        } catch (UnsupportedOperationException ex) {
            System.out.println("toList result = unmodifiable");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -d out17 FeatureOriginDemo.java
java -cp out17 FeatureOriginDemo
```

Stdout:

```text
foundation = JAVA_5_FOUNDATION
all topics = [generics, enum, annotations]
selected = [generics, annotations]
generic first = generics
optional empty = false
separator = ========
topic = generics
topic = annotations
toList result = unmodifiable
```

Trong ví dụ:

| Dòng hoặc cơ chế | Nguồn gốc cần phân biệt |
| --- | --- |
| `enum Origin` | Nền tảng enum Java 5 |
| `static <T> T first(List<T> values)` | Phương thức generic Java 5 |
| `for (String topic : selected)` | Enhanced for Java 5 |
| `List.of(...)` | API Java 9 |
| `stream()`, lambda `->` và `findFirst()` | Các cơ chế/API thuộc nền tảng xử lý Java 8 |
| `firstSelected.isEmpty()` | Phương thức từ Java 11 |
| `"=".repeat(8)` | Phương thức từ Java 11 |
| `Stream.toList()` | Phương thức từ Java 16 |

Không có mâu thuẫn khi một chương trình sử dụng tất cả các phần này. Java hiện đại được xây bằng các cơ chế và API tích lũy qua nhiều phiên bản. Điều cần tránh là gán toàn bộ đoạn mã cho mốc của chủ đề đang giải thích.

Giá trị enum `JAVA_5_FOUNDATION` trong ví dụ chỉ là nhãn dữ liệu minh họa; nó không phải một cơ chế Java tự phân tích nguồn gốc tính năng. Việc phân loại cần dựa trên tài liệu và chữ ký thật.

## 7. Dùng --release để kiểm chứng mức API đích

Tài liệu [javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) mô tả `--release` để biên dịch theo mức nền tảng được chỉ định trong các mức mà trình biên dịch hỗ trợ. Nó phối hợp kiểm tra cú pháp, dạng mã lớp và API nền tảng của mức đích.

Thử biên dịch cùng chương trình với:

```shell
javac --release 11 -d out11 FeatureOriginDemo.java
```

Đây là **phép thử dự kiến thất bại**, không phải lệnh chạy thành công của chương trình. Trình biên dịch không tìm được `Stream.toList()` vì API Java 11 chưa có phương thức đó.

Phần cốt lõi của thông báo lỗi:

```text
cannot find symbol
symbol: method toList()
location: interface Stream<String>
```

Vị trí dòng, cách trình bày và ngôn ngữ của thông báo có thể khác theo môi trường. Điều được kiểm chứng là phương thức `toList` không thuộc API nền tảng Java 11.

Các lời gọi `List.of`, `String.repeat` và `Optional.isEmpty` trong ví dụ không phải nguyên nhân của phép thử Java 11 này vì chúng đã có ở mức đó. Nhờ chỉ giữ một điểm vượt mức, ví dụ cho thấy lỗi có nguyên nhân cụ thể.

### 7.1. Vì sao máy cài JDK mới vẫn có thể báo thiếu phương thức?

JDK dùng để chạy trình biên dịch và mức Java mà mã đang nhắm tới không nhất thiết giống nhau.

Một JDK mới có thể biết `Stream.toList` trong thư viện của chính nó, nhưng khi biên dịch với `--release 11`, nó phải kiểm tra mã theo API nền tảng của Java 11. Việc từ chối là đúng và có ích.

Ngược lại, nếu chỉ biên dịch theo JDK đang cài mà không giữ mức đích của dự án, một người phát triển có thể vô tình thêm lời gọi mới hơn mức môi trường triển khai cho phép.

### 7.2. --release không cài môi trường chạy cũ

Phép thử không yêu cầu chạy chương trình trên JDK 11 thật và không cài thêm môi trường nào. Nó sử dụng cơ chế kiểm tra mức nền tảng của trình biên dịch hiện tại.

`--release` cũng không phải bộ mô phỏng toàn bộ hành vi môi trường triển khai. Chạy kiểm chứng trên runtime mà dự án hỗ trợ vẫn có giá trị, nhất là khi có hành vi thư viện, dữ liệu vùng, hệ điều hành hoặc phụ thuộc ngoài liên quan.

Không phải mọi JDK đều hỗ trợ nhắm đến mọi phiên bản Java trong lịch sử. Dùng `javac --help` để biết các mức được hỗ trợ. Bài không yêu cầu ép một JDK hiện đại biên dịch về Java 5.

### 7.3. Không đánh đồng --source, --target và --release

Kiểm tra cú pháp nguồn hoặc đặt phiên bản mã lớp không tự đồng nghĩa đã kiểm tra đúng tập API nền tảng đích.

`--release` là lựa chọn phù hợp khi muốn kiểm soát đồng thời những phần này theo một mức phát hành được hỗ trợ. Không dùng việc “cú pháp này biên dịch được” làm bằng chứng rằng mọi lời gọi API đều tồn tại trên runtime thấp hơn.

Mặt khác, `--release` không xác định phiên bản tối thiểu của mọi thư viện bên ngoài. Phụ thuộc ngoài còn cần cấu hình và kiểm chứng riêng; không có cơ chế nào biến một JAR mới thành tương thích chỉ nhờ giảm mức Java nguồn của mã ứng dụng.

## 8. Nếu phải thay một lời gọi, đọc cả hợp đồng

Giả sử một dự án hợp lệ đang nhắm Java 11 nên không dùng được `Stream.toList`. Có thể chọn cách thu thập khác tồn tại ở mức đích, nhưng không thay máy móc chỉ để hết lỗi biên dịch.

Ví dụ minh họa hai ý định khác nhau:

```java
List<String> mutableResults = names.stream()
        .filter(name -> name.length() > 2)
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));

List<String> resultsWithCollector = names.stream()
        .filter(name -> name.length() > 2)
        .collect(java.util.stream.Collectors.toList());
```

Đây là đoạn rời với `names` đã có. Cách đầu yêu cầu một `ArrayList` có thể sửa. Với `Collectors.toList`, không nên dựa vào giả định kiểu triển khai hoặc tính có thể sửa nếu hợp đồng không bảo đảm điều đó.

Trong khi đó, `Stream.toList` công bố kết quả không cho sửa. Nếu mã trước đó gọi `add` trên danh sách thu được, đổi sang `toList` có thể làm hành vi thay đổi dù tên hai API đều chứa `toList`.

Điểm học tập là **mốc phiên bản và ngữ nghĩa đều cần kiểm tra**. Đáp ứng phiên bản tối thiểu nhưng thay sai hợp đồng vẫn là một lỗi.

Nếu dự án đã chọn Java 17 hoặc cao hơn và các ràng buộc đều phù hợp, không cần tránh `Stream.toList` chỉ vì đang học generics. Hãy dùng tiện ích hiện đại và ghi đúng nguồn gốc.

## 9. Đọc ví dụ, tài liệu và mã dự án một cách có phương pháp

Với một đoạn mã cần phân loại, có thể làm lần lượt:

1. Tách cú pháp đặc biệt khỏi lời gọi phương thức.
2. Ghi tên đầy đủ của lớp/giao diện và chữ ký đang gọi.
3. Xác định mốc cơ chế ngôn ngữ bằng tài liệu chính thức.
4. Xác định mốc thành viên bằng `Since`, không chỉ mốc lớp.
5. Kiểm tra mức Java đích của dự án.
6. Biên dịch ở mức đó để phát hiện những API vượt mức.
7. Nếu cần điều chỉnh, so sánh hợp đồng trước–sau.
8. Nêu rõ cơ sở của kết luận thay vì suy đoán từ phong cách mã.

Ví dụ mô tả chính xác:

> Đoạn mã minh họa generics từ Java 5 và dùng `List.of` của Java 9 để tạo dữ liệu; chương trình được biên dịch ở mức Java 17.

Mô tả gây nhầm:

> Đây là toàn bộ cú pháp/API của Java 5 vì mục bài học là Java 5.

Một tài liệu hiện tại có thể bổ sung nhiều API mới vào lớp có nguồn gốc cũ. Đó là lý do phải đọc chi tiết, không lấy trang JDK hiện tại rồi suy rằng toàn bộ thành viên đã tồn tại từ ngày đầu của lớp.

## 10. Nguồn gốc khác với trạng thái sử dụng hiện tại

Ba nhận định phải tách:

| Nhận định | Câu hỏi thực sự |
| --- | --- |
| “Có từ Java 5” | Nó bắt đầu xuất hiện ở mốc nào? |
| “Còn áp dụng hiện nay” | Nó còn thuộc hợp đồng và phù hợp cách dùng hiện hành không? |
| “Phù hợp nhất cho yêu cầu này” | Nó có đáp ứng ràng buộc và mục đích cụ thể không? |

Một cơ chế xuất hiện từ lâu như generics hoặc enum vẫn là nền tảng hiện tại. Một API mới hơn không tự động là lựa chọn đúng cho mọi bài toán.

Cũng không suy rằng có trong JDK hiện tại nghĩa là mọi cách dùng đều được khuyến khích. Cần đọc trạng thái deprecated, mô tả và hướng dẫn cụ thể khi lựa chọn API. Phạm vi bài này tập trung vào các kiến thức còn dùng, không cần học những công cụ đã được thay thế chỉ để lấp đầy một bảng lịch sử.

Với tính năng từng có giai đoạn preview, cần phân biệt lần xuất hiện thử nghiệm với lần trở thành tính năng chính thức khi nêu phiên bản tối thiểu. Không coi một ví dụ phải bật preview là tương đương một tính năng ổn định mặc định. Nếu chưa cần tính năng đó cho bài toán, không mở rộng bảng lịch sử một cách tùy tiện.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nhìn `List<String>` rồi gọi toàn bộ dòng là Java 5 | Gán nhầm `List.of` hoặc tiện ích khác | Tách cơ chế kiểu và lời gọi API |
| Lấy `Since` của lớp cho mọi phương thức | Bỏ sót thành viên thêm sau | Mở đúng chi tiết phương thức |
| Thấy Stream nên cho `toList` có từ Java 8 | Lỗi biên dịch ở mức API thấp hơn | Kiểm tra `Since: 16` của phương thức |
| Dùng JDK mới nhưng quên mức đích | Vô tình phụ thuộc API mới hơn triển khai | Cố định mức biên dịch phù hợp |
| Chỉ giảm phiên bản mã lớp | Có thể vẫn dùng API không tồn tại ở runtime đích | Kiểm tra bằng mức nền tảng phù hợp |
| Nghĩ `--release` kiểm soát mọi JAR bên ngoài | Bỏ sót yêu cầu của phụ thuộc | Kiểm tra phụ thuộc riêng |
| Thay API bằng tên gần giống mà không đọc hợp đồng | Thay đổi tính có thể sửa/null/thứ tự | So sánh ngữ nghĩa |
| Coi mọi tính năng lâu đời đều lỗi thời | Bỏ qua nền tảng đang sử dụng | Phân biệt lịch sử và mức phù hợp hiện tại |
| Coi mọi annotation có cùng mốc | Nhầm annotation cụ thể với cơ chế | Xác minh nguồn và phiên bản của annotation |
| Gán lịch sử từ một ví dụ không ghi baseline | Kết luận thiếu căn cứ | Ghi rõ nguồn và mức biên dịch |

## 12. Tự kiểm chứng và thực hành

1. Phân tích `List<String> values = List.of("A")` thành cơ chế kiểu và lời gọi API. Nêu mốc của từng phần.
2. So sánh `List.of` với `List.copyOf` trong tài liệu; kiểm tra hai mốc khác nhau trên cùng giao diện.
3. Tìm `Since` đầu trang `Optional` và `Since` của `isEmpty`. Giải thích vì sao không mâu thuẫn.
4. Chạy chương trình ở `--release 17` rồi thực hiện phép biên dịch dự kiến thất bại ở `--release 11`. Xác định đúng biểu tượng bị thiếu.
5. Thay riêng `Stream.toList` bằng một cách thu thập phù hợp yêu cầu Java 11. Kiểm tra lại tính có thể sửa của kết quả, không chỉ kết quả các phần tử.
6. Chọn một phương thức mới trên `String` và đọc `Since` của chính nó. Không dùng mốc của lớp `String` thay câu trả lời.
7. Tìm một đoạn mã có lambda gửi cho `Callable`. Phân biệt mốc của giao diện tác vụ với mốc của cú pháp lambda.
8. Trong một dự án hiện đại, xác định JDK dùng để biên dịch, mức Java đích và runtime được hỗ trợ. Đây có thể là ba thông tin cần đọc riêng.
9. Với một annotation framework, chỉ ra thư viện cung cấp và phiên bản thư viện; không gán phiên bản chỉ bằng tuổi của cú pháp `@`.
10. Viết một mô tả ngắn cho ví dụ dùng nhiều mốc: chủ đề nền tảng nào được minh họa, tiện ích về sau nào được dùng và mức Java nào đã kiểm chứng.

Phân loại đúng nguồn gốc giúp dùng Java hiện đại có chủ đích: giữ nền tảng kiểu và mô hình từ Java 5, nhận diện những tiện ích bổ sung và xác minh chính xác yêu cầu API của mã đang viết.
