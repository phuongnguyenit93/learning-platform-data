# Bản sao qua copy() và giới hạn thay đổi qua minimalCompletionStage() trong Java

## Mục tiêu

Từ Java 9, **CompletableFuture** cung cấp hai phương thức hữu ích khi chia sẻ một tác vụ bất đồng bộ cho mã bên ngoài:

- **copy()** tạo một CompletableFuture mới nhận kết quả hoặc lỗi hoàn tất từ future nguồn.
- **minimalCompletionStage()** tạo một CompletionStage tối giản để bên nhận sử dụng các thao tác kết hợp mà không được trao trực tiếp các phương thức thay đổi trạng thái của CompletableFuture nguồn.

Hai phương thức đều giúp kiểm soát quyền sở hữu khi công bố kết quả bất đồng bộ, nhưng chúng có kiểu trả về và mức độ bảo vệ khác nhau. Bài này giải thích hành vi, cách chọn API và các giới hạn cần nhớ trong Java 17+.

## 1. Vấn đề khi trả trực tiếp CompletableFuture

Một **CompletableFuture<T>** vừa đại diện cho kết quả sẽ có trong tương lai, vừa cho phép người gọi tác động đến trạng thái hoàn tất của nó.

Bên nhận có thể gọi các phương thức như:

- **complete(value)** để tự hoàn tất future.
- **completeExceptionally(error)** để tự hoàn tất bằng lỗi.
- **cancel(mayInterruptIfRunning)** để hủy future.
- **obtrudeValue(value)** hoặc **obtrudeException(error)** để ghi đè kết quả quan sát được.
- **orTimeout(...)** và **completeOnTimeout(...)** để áp dụng chính sách timeout lên chính future đó.

Nếu một lớp trả trực tiếp future nội bộ của mình, bên gọi có thể hoàn tất hoặc hủy future trước khi công việc thật sự kết thúc. Điều này làm thay đổi đối tượng mà lớp sở hữu và có thể phá vỡ logic của những thành phần khác đang dùng cùng future.

Ví dụ về rủi ro:

```java
CompletableFuture<String> internal = startRequest();

// Không nên công bố trực tiếp nếu caller không được quyền
// điều khiển trạng thái hoàn tất của internal.
return internal;
```

Nếu caller gọi **complete("fake result")**, future nội bộ có thể bị hoàn tất bằng giá trị do caller chọn. Các callback gắn vào cùng future cũng quan sát kết quả đó.

Java 9 bổ sung **copy()** và **minimalCompletionStage()** để tạo ranh giới giữa future mà lớp sở hữu và đối tượng được công bố cho bên nhận.

## 2. CompletableFuture.copy()

**copy()** trả về một **CompletableFuture<T>** mới. Future mới được hoàn tất với cùng kết quả hoặc lỗi khi future nguồn hoàn tất.

Ví dụ:

```java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> copy = source.copy();

source.complete("server result");

System.out.println(source.join());
System.out.println(copy.join());
```

Stdout:

```text
server result
server result
```

Hai future có trạng thái hoàn tất riêng. Khi nguồn hoàn tất trước, bản sao nhận kết quả tương ứng. Tuy nhiên, vì kiểu trả về vẫn là **CompletableFuture<T>**, bên nhận có thể hoàn tất bản sao bằng phương thức của CompletableFuture.

### Hoàn tất bản sao không hoàn tất nguồn

Ví dụ sau chủ động hoàn tất bản sao trước khi nguồn có kết quả:

```java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> copy = source.copy();

copy.complete("local result");
source.complete("server result");

System.out.println(source.join());
System.out.println(copy.join());
```

Stdout:

```text
server result
local result
```

Bản sao đã được hoàn tất bằng giá trị riêng nên lần hoàn tất sau đó từ nguồn không thay đổi kết quả của bản sao. Ngược lại, việc hoàn tất bản sao không làm thay đổi future nguồn.

Điều này có nghĩa **copy() không phải một view bất biến**. Nó tạo một CompletableFuture độc lập mà bên nhận vẫn có thể điều khiển. Mục đích của nó là bảo vệ trạng thái của future nguồn khỏi thao tác trên bản sao.

### Khi nào dùng copy()?

Dùng **copy()** khi bên nhận cần một đối tượng có kiểu CompletableFuture, chẳng hạn để tương thích với API hiện có hoặc khi caller cần một future mà họ có thể hoàn tất/hủy riêng.

Các thao tác thay đổi trên bản sao không thay đổi trạng thái hoàn tất của nguồn. Tuy nhiên, cần nhớ rằng bản sao vẫn là một CompletableFuture có thể thay đổi.

## 3. CompletableFuture.minimalCompletionStage()

**minimalCompletionStage()** trả về **CompletionStage<T>**. Đây là giao diện nhỏ hơn CompletableFuture, tập trung vào việc kết hợp và quan sát kết quả bất đồng bộ.

CompletionStage cung cấp các thao tác như:

- **thenApply()**, **thenAccept()**, **thenRun()**.
- **thenCompose()** để nối một tác vụ bất đồng bộ khác.
- **thenCombine()**, **thenAcceptBoth()** để kết hợp hai stage.
- **exceptionally()**, **handle()**, **whenComplete()** để xử lý lỗi hoặc quan sát kết quả.

CompletionStage không công bố các phương thức thay đổi trạng thái đặc thù của CompletableFuture như **complete()**, **cancel()** hay **obtrudeValue()**.

Ví dụ:

```java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("server result");

CompletionStage<String> view = source.minimalCompletionStage();

CompletionStage<Integer> length =
        view.thenApply(String::length);

System.out.println(length.toCompletableFuture().join());
```

Stdout:

```text
13
```

Bên nhận có thể tiếp tục xây dựng pipeline bất đồng bộ nhưng không nhận trực tiếp kiểu CompletableFuture của nguồn.

### Không nên ép kiểu view về CompletableFuture

Không viết logic dựa trên giả định rằng đối tượng trả về bởi **minimalCompletionStage()** có thể ép kiểu an toàn thành CompletableFuture. Hợp đồng API trả về CompletionStage và chỉ hứa các thao tác của abstraction đó.

Hãy giữ kiểu **CompletionStage<T>** trong chữ ký API nếu mục tiêu là công bố một stage để quan sát/kết hợp. Không dùng cast để tìm cách lấy lại quyền thay đổi trạng thái của future nguồn.

## 4. toCompletableFuture() trên minimal stage

CompletionStage có phương thức **toCompletableFuture()** để hỗ trợ tương tác với API yêu cầu CompletableFuture.

Khi gọi phương thức này trên minimal stage, bên nhận nhận được một CompletableFuture riêng có thể thao tác độc lập. Hoàn tất hoặc hủy future được chuyển đổi không làm thay đổi future nguồn.

Ví dụ:

```java
CompletableFuture<String> source = new CompletableFuture<>();
CompletionStage<String> view = source.minimalCompletionStage();

CompletableFuture<String> detached = view.toCompletableFuture();

detached.complete("local result");
source.complete("server result");

System.out.println(source.join());
System.out.println(view.toCompletableFuture().join());
System.out.println(detached.join());
```

Stdout:

```text
server result
server result
local result
```

Trong ví dụ:

1. **source** là future do lớp sở hữu.
2. **view** là CompletionStage tối giản được công bố.
3. **detached** là CompletableFuture được tạo để tương thích với API cần kiểu đó.
4. Caller hoàn tất **detached** bằng giá trị riêng.
5. Future nguồn vẫn hoàn tất bằng kết quả thật; view tiếp tục phản ánh kết quả của nguồn.

Mỗi lần gọi **toCompletableFuture()** trên minimal stage có thể tạo một future chuyển đổi riêng. Không nên dùng nó để lấy tham chiếu tới đối tượng nguồn hoặc giả định các lần gọi trả về cùng một object.

## 5. So sánh copy() và minimalCompletionStage()

| Tiêu chí | **copy()** | **minimalCompletionStage()** |
|---|---|---|
| Có từ | Java 9 | Java 9 |
| Kiểu trả về | **CompletableFuture<T>** | **CompletionStage<T>** |
| Mục tiêu | Tạo future hoàn tất độc lập | Công bố stage với API tối giản |
| Bên nhận gọi thenApply/thenCompose | Có | Có |
| Bên nhận gọi complete/cancel trực tiếp trên giá trị trả về | Có | Không qua kiểu CompletionStage |
| Bên nhận có thể lấy CompletableFuture riêng | Đã là CompletableFuture | Qua **toCompletableFuture()** |
| Thay đổi bản trả về có làm hoàn tất nguồn không? | Không | Không; future chuyển đổi cũng độc lập |

### Quy tắc lựa chọn

- Chọn **copy()** khi hợp đồng API cần trả về CompletableFuture và caller được phép quản lý trạng thái của bản sao.
- Chọn **minimalCompletionStage()** khi chỉ muốn công bố khả năng kết hợp/quan sát kết quả và muốn giới hạn bề mặt API mà caller nhìn thấy.
- Giữ future nguồn ở bên trong lớp sở hữu khi caller không cần quyền hoàn tất hoặc hủy nó.
- Nếu API cần trả CompletionStage, không cần chuyển sang CompletableFuture chỉ để dùng **thenApply()** hoặc **thenCompose()**, vì các thao tác đó đã có trên CompletionStage.

## 6. Ví dụ thiết kế API dịch vụ

Một dịch vụ có thể giữ CompletableFuture nội bộ và chỉ công bố CompletionStage:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class UserService {
    private final CompletableFuture<String> userResult =
            CompletableFuture.supplyAsync(() -> "Ada");

    public CompletionStage<String> findUser() {
        return userResult.minimalCompletionStage();
    }
}
```

Caller sử dụng:

```java
CompletionStage<Integer> nameLength =
        userService.findUser().thenApply(String::length);
```

Caller có thể kết hợp stage vào pipeline của họ. Chữ ký API không trao trực tiếp các phương thức thay đổi trạng thái của CompletableFuture nội bộ.

Nếu caller thực sự cần CompletableFuture để tích hợp với thư viện khác, API có thể chủ động cung cấp bản sao:

```java
public CompletableFuture<String> findUserFuture() {
    return userResult.copy();
}
```

Cần lựa chọn một hợp đồng rõ ràng: CompletionStage cho API hướng tới composition; CompletableFuture bản sao cho API cần kiểu future cụ thể và cho phép caller thao tác độc lập trên bản đó.

## 7. Giới hạn quan trọng: đây không phải deep copy

**copy()** sao chép trạng thái hoàn tất của future, không sao chép sâu object được lưu trong kết quả.

Ví dụ:

```java
CompletableFuture<List<String>> source =
        CompletableFuture.completedFuture(
                new ArrayList<>(List.of("Ada")));

CompletableFuture<List<String>> copy = source.copy();

copy.join().add("Grace");

System.out.println(source.join());
```

Stdout:

```text
[Ada, Grace]
```

Cả hai future chứa cùng tham chiếu tới một List. Thay đổi List thông qua bản sao vẫn được nhìn thấy qua nguồn.

**minimalCompletionStage()** cũng không tự sao chép object kết quả. Nó giới hạn cách thao tác trên stage, không biến object T thành immutable.

Nếu kết quả là object mutable và caller không được phép sửa dữ liệu dùng chung, cần áp dụng thêm biện pháp ở tầng dữ liệu:

- Trả về object immutable.
- Tạo defensive copy của kết quả trước khi công bố.
- Dùng collection immutable hoặc bản sao collection phù hợp.
- Thiết kế DTO chỉ chứa dữ liệu không cho caller thay đổi.

Bảo vệ trạng thái hoàn tất của future và bảo vệ object kết quả là hai yêu cầu riêng.

## 8. Xử lý exception, cancellation và timeout

Kết quả lỗi của future nguồn cũng được truyền sang bản sao hoặc stage tối giản khi nguồn hoàn tất bằng exception. Caller nên dùng các thao tác CompletionStage để xử lý lỗi:

```java
CompletionStage<String> safeView = source.minimalCompletionStage();

CompletionStage<String> recovered = safeView.exceptionally(error -> {
    return "fallback";
});
```

**copy()** trả về CompletableFuture độc lập nên caller có thể hủy hoặc áp dụng timeout cho bản sao. Các thao tác đó tác động lên bản sao, không tự động hủy tác vụ nguồn.

Tương tự, nếu caller gọi **toCompletableFuture().cancel(...)** trên một minimal stage, thao tác hủy áp dụng cho future chuyển đổi mà caller nhận được. Không được suy ra rằng tác vụ nguồn hoặc CompletableFuture nội bộ đã bị hủy.

Điều này đặc biệt quan trọng với các tác vụ I/O hoặc công việc nền: hủy một future đại diện không nhất thiết dừng công việc thực tế đang chạy. Muốn dừng tác vụ, ứng dụng cần có cơ chế hủy riêng phù hợp với nguồn công việc.

Nếu timeout chỉ nên giới hạn thời gian chờ của một caller, áp dụng timeout trên bản sao hoặc future chuyển đổi. Nếu timeout là chính sách của tác vụ nguồn, lớp sở hữu phải áp dụng nó lên future nguồn theo hợp đồng của dịch vụ.

## 9. Ví dụ Java hoàn chỉnh

Ví dụ sau minh họa việc hoàn tất bản sao độc lập, chuyển minimal stage thành future riêng và trường hợp bản sao tự nhận kết quả từ nguồn.

Tạo tệp **CopyAndMinimalStageDemo.java**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class CopyAndMinimalStageDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> copy = source.copy();
        CompletionStage<String> minimal =
                source.minimalCompletionStage();
        CompletableFuture<String> detached =
                minimal.toCompletableFuture();

        copy.complete("copy-local");
        detached.complete("detached-local");
        source.complete("source-result");

        System.out.println("source: " + source.join());
        System.out.println("copy: " + copy.join());
        System.out.println("minimal stage: "
                + minimal.toCompletableFuture().join());
        System.out.println("detached future: " + detached.join());

        CompletableFuture<String> anotherSource =
                new CompletableFuture<>();
        CompletableFuture<String> anotherCopy = anotherSource.copy();

        anotherSource.complete("propagated");
        System.out.println("copy follows source: " + anotherCopy.join());

        CompletableFuture<String> protectedSource =
                new CompletableFuture<>();
        CompletionStage<String> protectedView =
                protectedSource.minimalCompletionStage();

        protectedSource.complete("published");
        System.out.println("minimal view follows source: "
                + protectedView.toCompletableFuture().join());
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac --release 17 CopyAndMinimalStageDemo.java
java CopyAndMinimalStageDemo
```

Stdout chính xác:

```text
source: source-result
copy: copy-local
minimal stage: source-result
detached future: detached-local
copy follows source: propagated
minimal view follows source: published
```

Kết quả cho thấy bản sao và future chuyển đổi có thể được caller hoàn tất độc lập. Nếu caller không hoàn tất bản sao trước, bản sao nhận kết quả từ nguồn. Minimal stage vẫn phản ánh kết quả của nguồn và không công bố trực tiếp future nội bộ.

## 10. Lỗi thường gặp

1. **Cho rằng copy() là immutable**: copy trả CompletableFuture có thể được caller complete, cancel hoặc áp dụng timeout riêng.
2. **Cho rằng hoàn tất copy sẽ hoàn tất nguồn**: hai đối tượng có trạng thái hoàn tất độc lập; hoàn tất bản sao không thay đổi nguồn.
3. **Cho rằng minimalCompletionStage() trả CompletableFuture**: kiểu trả về là CompletionStage. Giữ đúng abstraction này và không ép kiểu.
4. **Cho rằng toCompletableFuture() trả lại future nguồn**: với minimal stage, future chuyển đổi là một đối tượng riêng để tương thích API.
5. **Cho rằng hai phương thức sao chép sâu kết quả**: object T có thể vẫn là cùng một tham chiếu mutable.
6. **Cho rằng cancel bản sao sẽ dừng tác vụ nguồn**: cancellation của bản sao không tự động hủy công việc nền hoặc future nguồn.
7. **Dùng CompletableFuture khi caller chỉ cần composition**: CompletionStage đã cung cấp thenApply, thenCompose, thenCombine và các thao tác xử lý lỗi.
8. **Dùng minimalCompletionStage() nhưng sau đó ép kiểu để lấy quyền complete**: cách làm này đi ngược mục tiêu giới hạn bề mặt API và không được hợp đồng CompletionStage bảo đảm.

## Kết luận

**copy()** tạo một CompletableFuture độc lập có thể nhận kết quả từ nguồn nhưng cũng có thể được caller hoàn tất riêng. **minimalCompletionStage()** công bố một CompletionStage tối giản, phù hợp khi caller chỉ cần kết hợp hoặc quan sát kết quả mà không cần trực tiếp điều khiển CompletableFuture nội bộ.

Hãy chọn theo hợp đồng API: dùng copy khi cần một CompletableFuture riêng; dùng minimalCompletionStage khi muốn công bố stage có bề mặt nhỏ hơn. Cả hai chỉ tách trạng thái hoàn tất, không deep-copy object kết quả và không tự dừng công việc nền khi bản sao bị hủy.
