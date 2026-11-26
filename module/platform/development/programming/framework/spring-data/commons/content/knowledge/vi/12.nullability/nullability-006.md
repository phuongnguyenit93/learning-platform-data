# Phạm vi package, type use và kế thừa annotation

Một annotation nullability chỉ có ý nghĩa khi xác định được nó thuộc bộ annotation nào, áp dụng ở vị trí nào và nằm trong phạm vi mặc định nào. Cùng một tên ngắn `@Nullable` có thể có cách dùng khác nhau nếu import từ các thư viện khác nhau.

Trong chương **Null và nullability** của Spring Data Commons (`SPRING_DATA_COMMONS`), bài này giải thích ba vấn đề: phạm vi package, annotation trên từng lần sử dụng kiểu và hợp đồng khi kế thừa hoặc override. Mục tiêu là đọc đúng chữ ký repository, projection và adapter, đồng thời giữ hợp đồng null rõ ràng khi refactor.

## 1. Xác định bộ annotation trước khi đọc ý nghĩa

Có hai cách khai báo thường gặp trong các thế hệ Spring:

| Cách khai báo | Annotation tiêu biểu | Đặc điểm cần nhớ |
| --- | --- | --- |
| JSpecify | `org.jspecify.annotations.NullMarked`, `Nullable`, `NonNull`, `NullUnmarked` | Có annotation phạm vi và annotation type use, diễn đạt được các thành phần của kiểu. |
| Spring nullability trước đây | `org.springframework.lang.NonNullApi`, `NonNullFields`, `Nullable`, `NonNull` | Mặc định package cho API/field và annotation trên khai báo; không có cùng khả năng biểu đạt generic element như JSpecify. |

Spring Framework 7 và Spring Data 4 dùng JSpecify trong cách khai báo nullability mới; bộ annotation `org.springframework.lang` trước đây được định hướng thay bằng JSpecify. Với dự án dùng phiên bản khác, cần áp dụng cách mà phiên bản đó hỗ trợ. Xem [Spring Data Commons — Null Handling](https://docs.spring.io/spring-data/commons/reference/repositories/null-handling.html).

Các ví dụ type use trong bài dùng import:

```java
import org.jspecify.annotations.Nullable;
```

Không thay bằng `org.springframework.lang.Nullable` rồi mặc định cú pháp generic và array vẫn có cùng nghĩa.

Bài không yêu cầu mọi dự án phải đổi phiên bản. Khi đọc một codebase, hãy bắt đầu bằng import và cấu hình nullability hiện có.

## 2. Annotation package áp dụng cho đúng package được khai báo

Với JSpecify, có thể đặt mặc định trong `package-info.java`:

```java
@NullMarked
package com.example.ticket.repository;

import org.jspecify.annotations.NullMarked;
```

Đoạn khai báo áp dụng mặc định cho các type usage thuộc phạm vi package `com.example.ticket.repository`, trừ khi có khai báo gần hơn thay đổi phạm vi.

Nó không tự phủ mọi package có cùng tiền tố tên.

Giả sử không có annotation mặc định nào khác ở module, type hoặc method:

| Package của một interface | Có được mặc định từ đoạn trên không? |
| --- | --- |
| `com.example.ticket.repository` | Có. |
| `com.example.ticket.repository.internal` | Không. |
| `com.example.ticket.repository.custom` | Không. |
| `com.example.ticket.service` | Không. |

Trong Java, các package có quan hệ tên gọi kiểu cha/con không tạo ra sự kế thừa annotation. Nếu muốn subpackage có cùng mặc định, cần khai báo phạm vi phù hợp cho subpackage đó hoặc dùng một phạm vi bao trùm khác được công cụ hỗ trợ.

Quy tắc package và các phạm vi của `@NullMarked` được giải thích trong [JSpecify Nullness User Guide](https://jspecify.dev/docs/user-guide/).

### Di chuyển file có thể đổi hợp đồng mà chữ ký vẫn nhìn giống nhau

Xét:

```java
Ticket lookup(String externalRef);
```

Trong package được null-marked, với kiểu cụ thể này, chữ ký mặc định nói rằng đầu vào và giá trị trả về không null.

Nếu chuyển interface sang package chưa đánh dấu và không có annotation phạm vi khác, cùng dòng mã không còn cung cấp cùng mặc định đó. Nullness có thể trở thành chưa được chỉ định.

Vì thế, refactor package không chỉ là thay tên import. Cần xem lại `package-info.java`, annotation trên type/method và những lời hứa mà phía gọi đang dựa vào.

## 3. Phạm vi gần hơn và NullUnmarked

JSpecify cho phép khai báo phạm vi trên type hoặc method, bên cạnh package. Trong các phạm vi bao quanh, khai báo `NullMarked` hoặc `NullUnmarked` gần nhất quyết định ngữ cảnh mặc định.

Ví dụ một interface Java làm gateway, không phải danh sách query method để framework suy diễn tên:

```java
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.NullUnmarked;
import org.jspecify.annotations.Nullable;

@NullMarked
public interface TicketGateway {

    Ticket require(String externalRef);

    @Nullable Ticket lookup(String externalRef);

    @NullUnmarked
    Ticket legacyLookup(String externalRef);
}
```

Cách đọc:

| Method | Tham số externalRef | Giá trị trả về |
| --- | --- | --- |
| `require` | Không null theo mặc định của type. | Không null theo mặc định của type. |
| `lookup` | Không null theo mặc định của type. | Có thể null do annotation tường minh. |
| `legacyLookup` | Chưa chỉ định bởi mặc định JSpecify tại method này. | Chưa chỉ định bởi mặc định JSpecify tại method này. |

`@NullUnmarked` không có nghĩa “mọi thứ đều được khai báo nullable”. Nó đưa phạm vi về trạng thái chưa chỉ định nullness cho những vị trí không có thông tin tường minh.

Sự khác biệt này có ích khi tiếp nhận code cũ từng phần: chưa biết hợp đồng khác với đã hứa rằng caller được phép truyền null.

Cũng không cần đặt `@NonNull` lên mọi kiểu cụ thể đã được mặc định non-null. Dùng annotation tường minh khi nó làm rõ một trường hợp cần thiết, thay vì lặp lại mặc định ở mọi dòng.

Chi tiết về phạm vi gần nhất được mô tả trong [khai báo NullMarked của JSpecify](https://github.com/jspecify/jspecify/blob/main/src/main/java/org/jspecify/annotations/NullMarked.java).

## 4. Type use: nullable ở container khác nullable ở phần tử

Annotation type use gắn vào một lần sử dụng kiểu cụ thể. Với generic, một chữ ký có nhiều vị trí kiểu cần đọc riêng.

Trong ngữ cảnh `@NullMarked`, xét các dạng dùng làm kiểu trả về, tham số hoặc field:

| Dạng kiểu | Tham chiếu List | Phần tử Ticket trong List |
| --- | --- | --- |
| `List<Ticket>` | Không null. | Không null. |
| `@Nullable List<Ticket>` | Có thể null. | Không null. |
| `List<@Nullable Ticket>` | Không null. | Có thể có phần tử null. |
| `@Nullable List<@Nullable Ticket>` | Có thể null. | Có thể có phần tử null. |

Ví dụ interface phục vụ dữ liệu nhập từ một nguồn ngoài:

```java
import java.util.List;

import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
interface ImportedTicketSource {

    List<Ticket> readValidated();

    @Nullable List<Ticket> readOptionalBatch();

    List<@Nullable Ticket> readBatchWithMissingSlots();
}
```

Ba method có ba hợp đồng:

- `readValidated`: có một List và mỗi phần tử là một Ticket không null.
- `readOptionalBatch`: bản thân batch có thể vắng mặt.
- `readBatchWithMissingSlots`: batch tồn tại nhưng một số vị trí có thể null.

Phía gọi `readBatchWithMissingSlots` không cần kiểm tra List có null theo hợp đồng, nhưng cần xử lý null khi lấy từng phần tử.

Một annotation đặt trên List không tự đi vào mọi kiểu bên trong List. Ngược lại, annotation trên Ticket trong dấu `<...>` không làm bản thân List trở thành nullable.

### Áp dụng vào query method

Một query trả `List<Ticket>` không cần đổi thành `List<@Nullable Ticket>` chỉ vì có thể không tìm thấy bản ghi. Không có bản ghi thường được biểu đạt bằng List rỗng, không phải một List chứa phần tử null.

Nếu custom adapter thật sự có khái niệm “vị trí trống”, hãy ghi hợp đồng riêng như ví dụ nguồn nhập. Đừng nhập ý nghĩa đó vào query collection một cách vô tình.

## 5. Mảng và kiểu viết đầy đủ cần chú ý vị trí annotation

### Null của mảng và null của phần tử

Trong ngữ cảnh null-marked:

| Dạng kiểu | Mảng có thể null? | Phần tử có thể null? |
| --- | --- | --- |
| `Ticket[]` | Không. | Không. |
| `@Nullable Ticket[]` | Không. | Có. |
| `Ticket @Nullable []` | Có. | Không. |
| `@Nullable Ticket @Nullable []` | Có. | Có. |

Có thể thể hiện trong chữ ký:

```java
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
interface ImportedTicketArrays {

    @Nullable Ticket[] nullableElements();

    Ticket @Nullable [] nullableArray();

    @Nullable Ticket @Nullable [] nullableArrayAndElements();
}
```

Ở dòng đầu, `@Nullable` đứng trước `Ticket`, nên nói về kiểu phần tử. Ở dòng thứ hai, annotation đứng trước cặp ngoặc mảng, nên nói về tham chiếu mảng.

Vì thế, đọc `@Nullable Ticket[]` thành “mảng có thể null” sẽ làm sai hợp đồng trong ví dụ này.

### Kiểu có tên đầy đủ

Với một kiểu viết đầy đủ, annotation type use của kiểu cần nằm sau dấu chấm cuối:

```java
java.util.@Nullable List<Ticket> legacyRead();
```

Tương tự, với nested type, dạng vị trí là:

```text
Outer.@Nullable Inner
```

Điểm quan trọng là annotation phải gắn vào type muốn mô tả, không gắn nhầm vào tên package hoặc kiểu bao ngoài.

Cú pháp generic, array và tên kiểu đầy đủ được minh họa trong [Spring Framework — Null-safety](https://docs.spring.io/spring-framework/reference/core/null-safety.html).

Các ví dụ ở bài đặt annotation vào chữ ký hoặc vị trí type được JSpecify nhận diện. Đừng mặc định mọi vị trí Java cho phép viết annotation, chẳng hạn kiểu gốc của local variable hay một cast, đều có ngữ nghĩa JSpecify tương tự.

## 6. Type variable cần được đọc theo bound và type argument

Với generic tự định nghĩa, không thể luôn rút gọn quy tắc thành “mọi T trong null-marked đều chắc chắn không null”.

Ví dụ:

```java
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
interface ValueBox<T extends @Nullable Object> {

    T get();
}
```

Bound cho phép type argument có nullness nullable. Kiểu trả về `T` giữ thông tin từ type argument được sử dụng.

Hai cách dùng có ý nghĩa khác nhau:

```text
ValueBox<Ticket>
ValueBox<@Nullable Ticket>
```

Trong dạng thứ hai, giá trị lấy ra có thể null. Việc interface có `@NullMarked` không xóa thông tin nullable của type argument.

Đây là **parametric nullness**: thông tin nullness đi theo kiểu được thay vào type variable. Khi thiết kế base repository hoặc wrapper generic, cần xét cả bound, type argument và những annotation tường minh, thay vì chỉ nhìn annotation trên package.

Quy tắc type variable và các thành phần của kiểu được định nghĩa trong [JSpecify Nullness Specification](https://jspecify.dev/docs/spec/).

## 7. Kế thừa hợp đồng không đồng nghĩa sao chép annotation

Cần phân biệt ba việc:

1. Một class hoặc interface được khai báo trong phạm vi null-marked.
2. Một type thừa hưởng member từ type khác.
3. Một method mới override hoặc redeclare method trước đó.

Một lớp lồng bên trong có thể nằm trong phạm vi khai báo của lớp bao ngoài. Một lớp con ở file khác không tự nằm trong phạm vi lexical của lớp cha chỉ vì có từ khóa `extends`.

Nếu không redeclare method, member được thừa hưởng vẫn có khai báo gốc để đọc hợp đồng. Khi override, khai báo mới cần thể hiện hợp đồng đúng theo annotation và mặc định tại vị trí mới.

### Ví dụ giữ nguyên hợp đồng nullable khi override

Giả sử gateway công bố rằng không tìm thấy ticket có thể trả null:

```java
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
interface TicketLookup {

    @Nullable Ticket find(String externalRef);
}
```

Adapter dùng repository trả Optional:

```java
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
final class TicketLookupAdapter implements TicketLookup {

    private final TicketRepository repository;

    TicketLookupAdapter(TicketRepository repository) {
        this.repository = repository;
    }

    @Override
    public @Nullable Ticket find(String externalRef) {
        return repository.findByExternalRef(externalRef)
            .orElse(null);
    }
}
```

Annotation `@Nullable` được ghi lại trên kiểu trả về của method override. Nếu bỏ nó trong class null-marked, dòng khai báo mới sẽ có mặc định non-null cho kiểu Ticket, trong khi phần thân vẫn có thể trả null.

Đó là sự không nhất quán cần được phát hiện và sửa, không phải điều annotation trên interface sẽ tự sao chép để cứu.

Spring hướng dẫn giữ annotation JSpecify trên method override khi muốn bảo toàn cùng ngữ nghĩa nullability. Khả năng suy luận hoặc kiểm tra quan hệ override còn tùy công cụ phân tích đang dùng.

### Inherited của Java không giải quyết việc này

`java.lang.annotation.Inherited` là meta-annotation với cơ chế tra cứu annotation trên class qua superclass. Nó không tự sao chép annotation của parameter hay return type sang method override, và không làm annotation trên interface tự truyền sang class triển khai.

Xem [Java API — Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html).

Không coi chữ “kế thừa” trong thiết kế API là bằng chứng rằng metadata annotation đã xuất hiện nguyên vẹn trên mọi khai báo mới.

## 8. Khi override, giữ khả năng thay thế của hợp đồng

Người gọi thông qua interface cha cần tiếp tục sử dụng được implementation con theo hợp đồng đã công bố.

Đối với cùng một kiểu dữ liệu cơ sở:

| Hợp đồng ở method gốc | Thay đổi tại method override | Đánh giá về khả năng thay thế |
| --- | --- | --- |
| Tham số chấp nhận null. | Tham số mới từ chối null. | Thu hẹp đầu vào, có thể phá hợp đồng. |
| Tham số yêu cầu không null. | Implementation xử lý được cả null. | Nới đầu vào, có thể tương thích. |
| Kết quả bảo đảm không null. | Kết quả mới có thể null. | Làm yếu lời hứa với caller. |
| Kết quả có thể null. | Implementation luôn trả không null. | Làm mạnh lời hứa, có thể tương thích. |

Đây là cách đánh giá hợp đồng, không có nghĩa chỉ dùng trình biên dịch Java thông thường là mọi sai lệch nullability đều bị từ chối.

Ví dụ, nếu interface cho phép:

```java
List<Ticket> search(@Nullable String query);
```

thì implementation không nên mặc nhiên dereference `query` như chắc chắn không null. Một caller hợp lệ theo interface có quyền truyền null.

Ngược lại, nếu interface hứa trả List không null, implementation không nên trả null khi không có kết quả; một List rỗng giữ được hợp đồng đó.

Annotation tường minh, công cụ phân tích và kiểm chứng hành vi cần thống nhất. Việc một override có thể biên dịch không chứng minh nó giữ đúng hợp đồng null.

## 9. Một repository có hợp đồng null rõ ràng

Ví dụ sau dùng JSpecify với phiên bản Spring Data hỗ trợ phù hợp:

```java
package com.example.ticket.repository;

import java.util.List;
import java.util.Optional;

import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;
import org.springframework.data.repository.CrudRepository;

@NullMarked
public interface TicketRepository extends CrudRepository<Ticket, Long> {

    Optional<Ticket> findByExternalRef(String externalRef);

    @Nullable Ticket findTicketByExternalRef(String externalRef);

    List<Ticket> findByStatus(TicketStatus status);
}
```

Giả sử `Ticket` đã được mapping, có `externalRef`, `status`, và query một kết quả đáp ứng kỳ vọng số lượng.

Cách đọc:

- Các tham số String và TicketStatus cụ thể có mặc định không null.
- `findByExternalRef` trả một Optional không null; không tìm thấy được biểu đạt bằng Optional empty.
- `findTicketByExternalRef` cho phép giá trị trả về là null.
- `findByStatus` trả List không null, với kiểu phần tử Ticket không null theo khai báo JSpecify.

Hai method tìm theo externalRef dùng hai tên khác nhau để minh họa hai dạng hợp đồng. Không thể khai báo hai method chỉ khác kiểu trả về nhưng có cùng tên và danh sách tham số Java.

Annotation trên kết quả không tự thay đổi điều kiện truy vấn. `@Nullable` trên một tham số cũng không tự có nghĩa “bỏ qua điều kiện nếu nhận null”; ý nghĩa query còn thuộc module và cách định nghĩa truy vấn.

### Projection và kiểu của getter

Với một projection được module hỗ trợ, có thể biểu đạt một thuộc tính vắng mặt tại getter:

```java
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
interface TicketSummary {

    Long getId();

    @Nullable String getAssigneeName();
}
```

Đây là hợp đồng getter có thể trả null. Nó không tự tạo mapping, không bảo đảm mọi store hỗ trợ cùng cơ chế projection và không làm mọi trường khác trong đối tượng trở thành nullable.

## 10. Nếu dự án dùng bộ annotation Spring trước đây

Với mô hình `org.springframework.lang`, một package có thể đặt:

```java
@NonNullApi
package com.example.ticket.repository;

import org.springframework.lang.NonNullApi;
```

`@NonNullApi` đặt mặc định cho tham số và giá trị trả về của API. Nó không tự là mặc định non-null cho mọi field; `@NonNullFields` là annotation riêng cho mục đích đó.

Ví dụ method với bộ annotation này:

```java
import org.springframework.lang.Nullable;

@Nullable
Ticket findTicketByExternalRef(String externalRef);
```

Trong cách khai báo cũ, annotation mô tả return value của method. Không lấy cú pháp `List<@Nullable Ticket>` từ ví dụ JSpecify rồi giữ import `org.springframework.lang.Nullable`: bộ annotation cũ không cung cấp cùng khả năng type use cho generic argument.

Những giới hạn này được nêu trong [Spring Framework 6.2 — Null-safety](https://docs.spring.io/spring-framework/reference/6.2/core/null-safety.html).

Khi chuyển bộ annotation, cần đọc lại hợp đồng ở từng vị trí:

- Mặc định đang áp dụng cho API hay cả field?
- Annotation trước array đang nói về array hay phần tử?
- Generic argument có được mô tả tường minh trước đây không?
- Method override có cần ghi lại annotation?
- Công cụ và hạ tầng runtime có nhận diện bộ annotation mới không?

Không coi đổi import là một phép thay thế chuỗi luôn giữ nguyên ngữ nghĩa.

## 11. Tách hợp đồng Java, kiểm tra runtime và ràng buộc lưu trữ

Ba lớp sau có thể phối hợp nhưng không thay thế nhau:

| Lớp | Vai trò |
| --- | --- |
| Annotation nullability | Mô tả kiểu và hợp đồng cho người đọc, công cụ và framework có hỗ trợ. |
| Kiểm tra static hoặc runtime | Phát hiện một số hành vi vi phạm hợp đồng theo cấu hình và phạm vi công cụ. |
| Mapping/ràng buộc tại store | Quy định dữ liệu có thể được lưu hoặc truy vấn như thế nào. |

`@NullMarked` không tự tạo migration NOT NULL. `@Nullable` không tự đổi schema thành cho phép null.

Tương tự, retention runtime của annotation chỉ làm metadata có thể được đọc ở runtime; nó không tự chèn một câu kiểm tra null vào mọi method Java.

Spring Data có cơ chế kiểm tra nullability cho query method trong các cấu hình được hỗ trợ. Không suy từ đó rằng mọi custom fragment, getter projection hoặc mọi phần tử lồng trong collection đều được kiểm tra đệ quy giống nhau.

Công cụ phân tích cũng có mức hỗ trợ khác nhau cho generic, array và override. Cần xác định công cụ đang dùng cùng chế độ cấu hình, thay vì xem việc không có cảnh báo là bằng chứng duy nhất.

## 12. Kiểm tra hợp đồng khi đổi package hoặc redeclare method

Giả sử một interface được chuyển từ package `repository` sang `repository.custom`. Một trình tự kiểm tra nội dung hợp đồng hợp lý là:

1. Xác định bộ annotation và phiên bản framework mà dự án sử dụng.
2. Xác định mặc định ở package mới, không suy từ tiền tố tên package.
3. Xem annotation gần hơn ở type hoặc method.
4. Đọc từng vị trí type use: container, phần tử, array, generic bound.
5. Nếu redeclare/override, đối chiếu với hợp đồng gốc.
6. Xác minh phần triển khai trả đúng biểu diễn vắng mặt đã công bố.
7. Phân biệt phần công cụ kiểm tra được với hành vi cần kiểm chứng qua repository thực tế.

Các lỗi dễ gặp:

| Thay đổi | Hệ quả cần xem xét |
| --- | --- |
| Chuyển interface sang subpackage chưa đánh dấu | Mặc định null-marked từ package cũ không tự theo sang. |
| Bỏ Nullable ở override trong scope null-marked | Có thể vô tình công bố kết quả không null dù thân method còn trả null. |
| Đổi import Nullable sang bộ khác | Có thể đổi vị trí hợp lệ hoặc ngữ nghĩa type use. |
| Chỉ đánh dấu List nullable | Chưa biểu đạt phần tử nullable. |
| Chỉ đánh dấu phần tử nullable | Chưa cho phép tham chiếu List null. |
| Thêm NullUnmarked vào adapter | Chuyển mặc định thành chưa chỉ định, không tự kiểm chứng code cũ an toàn. |

## 13. Thực hành đọc đúng vị trí

Giả sử các chữ ký sau nằm trong một interface `@NullMarked` và dùng JSpecify:

| Chữ ký rút gọn | Hợp đồng cần đọc |
| --- | --- |
| `List<Ticket> read()` | List không null, phần tử Ticket không null. |
| `@Nullable List<Ticket> read()` | List có thể null, phần tử không null khi có List. |
| `List<@Nullable Ticket> read()` | List không null, có thể chứa phần tử null. |
| `@Nullable Ticket[] read()` | Mảng không null, có thể chứa phần tử null. |
| `Ticket @Nullable [] read()` | Mảng có thể null, phần tử không null khi có mảng. |
| `Optional<Ticket> find(String ref)` | Optional không null; ref cụ thể không null theo mặc định. |

Tiếp tục với hai tình huống:

**Tình huống A:** interface nằm trong `com.example.ticket.repository.custom`, còn chỉ `com.example.ticket.repository` có package annotation.

Không được tự gán mặc định của package kia cho interface này. Cần xem có annotation tại chính package, type, method hoặc phạm vi khác bao trùm hay không.

**Tình huống B:** method gốc trả `@Nullable Ticket`, implementation mới nằm trong class null-marked và vẫn dùng `orElse(null)`.

Nếu muốn giữ nguyên hợp đồng, ghi lại `@Nullable` trên kiểu trả về của override. Nếu muốn công bố non-null, phải thay đổi phần triển khai và bảo đảm thay đổi đó tương thích với use case, thay vì chỉ xóa annotation.

Với mỗi chữ ký, hãy xác định rõ ba thông tin: phạm vi mặc định đang có hiệu lực, vị trí type mà annotation gắn vào và hợp đồng gốc cần giữ khi có kế thừa.
