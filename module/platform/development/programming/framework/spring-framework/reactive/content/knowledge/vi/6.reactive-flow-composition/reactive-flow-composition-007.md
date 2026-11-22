# firstWithValue và firstWithSignal trong Project Reactor

> **Module:** Spring Framework – reactive · **Chủ đề cha:** Ghép và chia luồng. Bài học trình bày hai toán tử chọn một nguồn thắng trong cuộc đua nhiều Publisher: **firstWithSignal** chọn nguồn phát tín hiệu sớm nhất và **firstWithValue** chọn nguồn phát giá trị sớm nhất. Nội dung gồm cơ chế, ví dụ Java 17+ chạy được, kiểm thử bằng thời gian ảo, lỗi tổng hợp, cancellation và ứng dụng Spring WebFlux.

## 1. Sau bài học cần làm được gì?

1. Phân biệt chính xác giá trị **onNext** với tín hiệu **onComplete** (nguồn rỗng) và **onError** (nguồn lỗi).
2. Chọn đúng giữa **Mono.firstWithSignal**, **Mono.firstWithValue**, **Flux.firstWithSignal** và **Flux.firstWithValue** theo yêu cầu nghiệp vụ.
3. Dự đoán kết quả khi một nguồn hoàn thành rỗng, một nguồn báo lỗi, một nguồn phát dữ liệu chậm và một nguồn không bao giờ phát.
4. Giải thích vì sao với Flux, nguồn thắng bằng phần tử đầu **vẫn tiếp tục phát các phần tử sau**; các nguồn thua bị hủy nếu đã đăng ký.
5. Hiểu NoSuchElementException với **cause tổng hợp** khi không nguồn nào có giá trị, đồng thời biết cách kiểm tra từng nguyên nhân.
6. Viết test với **StepVerifier.withVirtualTime**, tránh test bằng Thread.sleep và những giả định không chắc chắn về thứ tự khi các nguồn phát gần như đồng thời.
7. Áp dụng race có kiểm soát cho truy vấn hai vùng/replica trong WebFlux và phân biệt nó với fallback tuần tự, merge, zip và concat.

**Quy tắc một câu:** firstWithSignal đua **tín hiệu**; firstWithValue đua **giá trị**. Hoàn thành rỗng và lỗi là tín hiệu nhưng không phải giá trị.

## 2. Nền tảng: Publisher, tín hiệu và subscription

**Mono<T>** có thể phát 0 hoặc 1 giá trị. **Flux<T>** có thể phát 0 đến nhiều giá trị. Một nguồn có thể:
- Gọi **onNext(value)** để phát dữ liệu; Reactive Streams không cho phép phát null.
- Gọi **onComplete** để kết thúc thành công; nếu chưa có onNext thì nguồn **rỗng**.
- Gọi **onError(error)** để kết thúc bằng lỗi.
- Nhận cancellation từ subscriber để ngừng phát và giải phóng tài nguyên nếu có hỗ trợ.

**onSubscribe** chỉ cung cấp Subscription và cơ chế request(n); nó **không phải** một trong ba tín hiệu thắng theo hợp đồng của firstWithSignal. Cần phân biệt **Mono.empty()** (hoàn thành rỗng) với **Mono.just(value)** (có dữ liệu) và **Mono.error(error)** (lỗi).

Với Publisher lạnh (**cold**), công việc thường chỉ bắt đầu khi có subscriber. Khi thực hiện cuộc đua, Reactor sắp xếp việc subscribe nhiều nguồn để quan sát tín hiệu; một nguồn đồng bộ có thể phát và thắng ngay, khiến các nguồn sau thậm chí chưa kịp được subscribe. Không dựa vào thứ tự truyền tham số làm quy tắc ưu tiên trong tình huống các nguồn đồng thời phát. Với nguồn nóng (**hot**), việc có phát trước subscription hay có replay hay không cũng ảnh hưởng kết quả.

~~~text
A: subscribe ── 100 ms ── onComplete (rỗng)
B: subscribe ── 300 ms ── onNext("B") ─ onComplete

firstWithSignal(A, B) → onComplete rỗng ở 100 ms
firstWithValue(A, B)  → onNext("B") ở 300 ms, rồi onComplete

C: subscribe ── 50 ms ── onError("offline")
D: subscribe ── 200 ms ── onNext("D") ─ onComplete

firstWithSignal(C, D) → onError("offline") ở 50 ms
firstWithValue(C, D)  → onNext("D") ở 200 ms, rồi onComplete
~~~

Các mốc thời gian chỉ minh họa **thứ tự**; Scheduler, hệ điều hành, độ trễ mạng, CPU và downstream demand có thể làm thời điểm thực thay đổi. Dùng virtual time cho test cần chính xác về logic.

## 3. firstWithSignal: nguồn phát bất kỳ tín hiệu sớm nhất

Javadoc xác định **firstWithSignal** chọn Publisher đầu tiên phát **onNext, onError hoặc onComplete**, rồi chuyển tiếp toàn bộ tín hiệu tiếp theo của Publisher đó. Đây là cuộc đua theo **kết quả quan sát đầu tiên**, kể cả khi kết quả đó là rỗng hoặc lỗi.

~~~java
Mono<String> fastestSignal = Mono.firstWithSignal(monoA, monoB);
Flux<String> fastestStreamSignal = Flux.firstWithSignal(fluxA, fluxB);
~~~

Các biến monoA, monoB, fluxA và fluxB trong đoạn này tượng trưng cho các Publisher có thật của ứng dụng; đây là **fragment về chữ ký API**, không phải chương trình độc lập.

Ví dụ:
- A = Mono.empty() hoàn thành ở 50 ms; B = Mono.just("OK") phát ở 200 ms. firstWithSignal **hoàn thành rỗng ở 50 ms**; B không có cơ hội trở thành winner.
- A = Mono.error(new IllegalStateException("down")) lỗi ở 50 ms; B phát "OK" sau 200 ms. firstWithSignal **trả lỗi của A**.
- A phát phần tử đầu lúc 80 ms rồi lỗi ở 300 ms; B phát giá trị lúc 150 ms. A đã thắng ở 80 ms, nên **lỗi về sau của A vẫn được chuyển tiếp**. Không chuyển sang B khi A lỗi sau khi thắng.

**Điểm mạnh:** có thể chọn phản hồi sớm nhất theo đúng định nghĩa “bất kỳ outcome nào”. **Rủi ro:** một nguồn rỗng/lỗi sớm có thể dừng kết quả mặc dù nguồn khác có dữ liệu tốt hơn. Vì vậy đây không phải lựa chọn mặc định cho bài toán “lấy giá trị sớm nhất”.

## 4. firstWithValue: nguồn phát onNext sớm nhất

**firstWithValue** chỉ chọn Publisher đầu tiên phát **giá trị onNext**. Nguồn hoàn thành rỗng hoặc báo lỗi trước khi phát giá trị **không thắng**; Reactor vẫn chờ khả năng có dữ liệu của các nguồn khác.

~~~java
Mono<String> firstUseful = Mono.firstWithValue(monoA, monoB);
Flux<String> firstUsefulStream = Flux.firstWithValue(fluxA, fluxB);
~~~

Ví dụ:
- A = Mono.empty() ở 50 ms; B phát "OK" ở 200 ms → firstWithValue phát **"OK"** ở 200 ms.
- A = Mono.error("down") ở 50 ms; B phát "OK" ở 200 ms → firstWithValue vẫn phát **"OK"**, không để lỗi A thắng.
- A phát "A1" ở 80 ms; B phát "B1" ở 100 ms → A thắng; nếu A là Flux, phần còn lại của A được chuyển tiếp cho downstream.

**Lưu ý với Flux:** khi Flux A đã thắng bằng một onNext, tất cả onNext/onComplete/onError về sau **của A** được chuyển tiếp. Toán tử **không phải** zip, merge hoặc hàm lấy duy nhất một phần tử từ tất cả nguồn. Muốn chỉ cần một phần tử, cân nhắc **next()** hoặc **take(1)** sau khi chọn.

### 4.1. Khi tất cả nguồn rỗng hoặc lỗi

Với **từ hai nguồn trở lên**, nếu không nguồn nào cung cấp được giá trị, firstWithValue báo **NoSuchElementException**. Javadoc mô tả exception này có một **cause composite** chứa một nguyên nhân ứng với mỗi nguồn:

- Nếu nguồn phát lỗi thật, nguyên nhân gốc được giữ ở chỉ số tương ứng.
- Nếu nguồn chỉ hoàn thành rỗng, một NoSuchElementException đại diện cho nguồn rỗng được ghi ở vị trí đó.
- Dùng **reactor.core.Exceptions.unwrapMultiple(topLevel.getCause())** để lấy danh sách nguyên nhân.

Điều này khác với firstWithSignal: nếu có một nguồn rỗng hoàn thành sớm, firstWithSignal sẽ hoàn thành rỗng; nếu có một nguồn lỗi sớm, firstWithSignal trả trực tiếp lỗi thắng. Với một nguồn duy nhất, đừng tự suy rộng quy tắc “lỗi gộp từ hai nguồn” sang trường hợp một nguồn; hãy xác định hợp đồng của overload và nguồn cụ thể.

### 4.2. Trường hợp never

~~~java
Mono<String> result = Mono.firstWithValue(
    Mono.<String>never(),
    Mono.<String>empty());
~~~

Nguồn thứ hai đã kết thúc rỗng, nhưng nguồn đầu **không bao giờ phát hay kết thúc**. firstWithValue có thể chờ vô hạn vì vẫn có khả năng một nguồn đem lại dữ liệu. Đặt ngân sách thời gian:

~~~java
Mono<String> bounded = Mono.firstWithValue(
        Mono.<String>never(),
        Mono.<String>empty())
    .timeout(Duration.ofSeconds(2));
~~~

Hai đoạn trên là fragment cần import reactor.core.publisher.Mono và java.time.Duration. Timeout có thể báo lỗi sau 2 giây nếu chưa nhận được kết quả; nó không tự biến kết quả thành giá trị hữu ích. Nếu muốn fallback khi timeout, thiết kế riêng theo nhu cầu.

## 5. Bảng đối chiếu các trường hợp quan trọng

| Trường hợp | firstWithSignal | firstWithValue |
| --- | --- | --- |
| A có giá trị trước B | Chọn A | Chọn A |
| A hoàn thành rỗng trước B có giá trị | Chọn A: hoàn thành rỗng | B thắng khi phát giá trị |
| A lỗi trước B có giá trị | Chọn A: trả lỗi A | B thắng khi phát giá trị |
| A phát giá trị rồi sau đó lỗi | A thắng và lỗi về sau của A được chuyển tiếp | A thắng và lỗi về sau của A được chuyển tiếp |
| Cả A và B đều rỗng | Hoàn thành rỗng theo nguồn nhanh hơn | NoSuchElementException có nguyên nhân của cả hai |
| A rỗng, B lỗi, không có giá trị | Kết quả theo tín hiệu đến trước | NoSuchElementException kèm nguyên nhân rỗng/lỗi |
| A và B đều lỗi trước khi phát giá trị | Lỗi đến trước thắng | NoSuchElementException với composite cause |
| A = never, B có giá trị | B thắng | B thắng |
| A = never, B chỉ rỗng/lỗi | B có thể thắng bằng hoàn thành/lỗi | Có thể đợi mãi: cần timeout |
| A và B gần như đồng thời phát | Tín hiệu được Reactor quan sát trước thắng | onNext được Reactor quan sát trước thắng |

**Không bảo đảm winner là nguồn truyền vào đầu tiên.** Với hai nguồn phát sát nhau, thứ tự có thể bị ảnh hưởng bởi scheduling; muốn có ưu tiên địa lý, độ mới hoặc độ tin cậy, hãy thiết kế tiêu chí đó tường minh. “Nhanh nhất” không đồng nghĩa “đúng nhất”.

## 6. Chọn một Mono hay chọn cả Flux?

### 6.1. Mono: một bản ghi/kết quả

~~~java
Mono<String> profile = Mono.firstWithValue(
    lookupFromRegionA(),
    lookupFromRegionB());
~~~

lookupFromRegionA và lookupFromRegionB ở đây là các hàm do ứng dụng định nghĩa trả Mono<String>. Khi một vùng lỗi nhanh và vùng khác trả profile muộn, vùng có profile có thể thắng. Ngược lại, nếu hai vùng đều không có dữ liệu, người gọi cần xử lý NoSuchElementException composite; không tự biến mọi lỗi thành 404.

### 6.2. Flux: nguồn thắng tiếp tục phát đến khi kết thúc

~~~java
Flux<String> winner = Flux.firstWithValue(
    Flux.just("A-1", "A-2").delayElements(Duration.ofMillis(200)),
    Flux.just("B-1", "B-2").delayElements(Duration.ofMillis(80)));
~~~

Nếu B phát B-1 trước thì kết quả là **B-1, B-2**, không có A-1/A-2. Flux winner được chọn bằng onNext đầu và **không chuyển nguồn lại** khi B về sau hoàn thành hoặc thất bại. Nếu chỉ muốn một phần tử, dùng winner.next() để có Mono<String>, với ý nghĩa lấy phần tử đầu và hủy phần còn lại.

### 6.3. Những vấn đề cancellation và side effect

Sau khi winner được xác định, các đối thủ đã subscribe thường nhận **cancel**; timer, publisher I/O và stream có hỗ trợ cancel có thể dừng. Nhưng điều này **không hoàn tác** tác vụ đã xảy ra ngoài tiến trình: HTTP request có thể đã đến server, database transaction có thể đã commit hoặc email có thể đã gửi.

**Chỉ đua các thao tác đọc, idempotent, hoặc những thao tác có chiến lược chống ghi trùng rõ ràng.** Không đua hai lệnh thanh toán hoặc ghi database rồi mặc định loser “không hề thực thi”. Với hot source, một sự kiện phát trước lúc được subscribe còn có thể bị bỏ lỡ; cần xác định cache/replay.

## 7. Phân biệt firstWithValue với các cách ghép khác

| API | Cơ chế | Khi dùng |
| --- | --- | --- |
| firstWithSignal | Đua onNext/onComplete/onError đầu tiên | Cần phản hồi sớm nhất **bất kể kết quả**. |
| firstWithValue | Đua onNext đầu tiên; bỏ qua nguồn chưa có dữ liệu | Cần dữ liệu hữu ích từ ít nhất một replica. |
| switchIfEmpty | Chỉ đăng ký fallback khi nguồn trước rỗng | Cache rồi database, giảm chi phí query phụ. |
| onErrorResume | Phục hồi một lỗi bằng Publisher khác | Fallback khi lỗi có loại được xác định. |
| concat / concatWith | Subscribe các nguồn theo thứ tự | Cần giữ thứ tự và tránh chạy nhiều nguồn cùng lúc. |
| merge / mergeWith | Phát giá trị từ **tất cả** các nguồn, có thể đan xen | Cần kết hợp các sự kiện của nhiều nguồn. |
| zip / zipWith | Đợi giá trị tương ứng từ **tất cả** các nguồn | Cần cả A và B để tạo kết quả. |
| timeout | Giới hạn thời gian chờ | Tránh forever khi có nguồn never / mạng treo. |

Cho cache và database có cùng kiểu dữ liệu:

~~~java
Mono<Profile> sequential = cache.find(id)
    .switchIfEmpty(Mono.defer(() -> database.find(id)));

Mono<Profile> raced = Mono.firstWithValue(
    cache.find(id),
    database.find(id));
~~~

Đây là **fragment**, giả định có cache.find(id), database.find(id) và kiểu Profile đã được định nghĩa. **sequential** không cần gọi database khi cache hit. **raced** có thể subscribe cả hai để lấy dữ liệu nhanh nhất, đổi lại tăng tải DB và có thể chọn bản cũ nếu cache/DB có version khác nhau. Nếu nguồn chính lỗi, switchIfEmpty tự nó không bắt lỗi; muốn phục hồi lỗi dùng onErrorResume có điều kiện.

**Không dùng firstWithValue khi cần dữ liệu của cả A và B.** Ví dụ tính điểm tổng hợp cần hai nguồn thì dùng Mono.zip(a, b), không hủy một nguồn theo winner. Còn nếu cần lựa chọn dữ liệu **đạt điều kiện**, filter/validate mỗi nguồn trước khi đua:

~~~java
Mono<Profile> selected = Mono.firstWithValue(
    regionA.find(id).filter(this::isAcceptable),
    regionB.find(id).filter(this::isAcceptable));
~~~

Ví dụ filter là fragment của service với phương thức isAcceptable(Profile) đồng bộ, không blocking. Giá trị không đạt chuẩn được đổi thành empty và không thắng firstWithValue.

## 8. Ví dụ hoàn chỉnh Java 17+ và Maven

Để thấy khác biệt của hai toán tử, chạy **Reactor Core 3.8.8** trong ứng dụng dòng lệnh Java 17. Chúng ta tạo hai cặp nguồn: một nguồn rỗng/lỗi sớm và một nguồn có giá trị muộn; cuối cùng thêm trường hợp Flux thắng nhưng vẫn phát phần tử tiếp theo.

### 8.1. Cấu trúc

~~~text
reactor-race/
├── pom.xml
├── src/main/java/com/example/race/RaceDemo.java
└── src/test/java/com/example/race/RaceTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactor-race</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. RaceDemo.java

**src/main/java/com/example/race/RaceDemo.java**

~~~java
package com.example.race;

import java.time.Duration;
import java.util.List;
import java.util.NoSuchElementException;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class RaceDemo {
    public static void main(String[] args) {
        // A rỗng sau ~20ms; B có giá trị sau ~80ms.
        Mono<String> emptyEarly = Mono.<String>empty()
            .delaySubscription(Duration.ofMillis(20));
        Mono<String> valueLater = Mono.just("OK")
            .delayElement(Duration.ofMillis(80));

        String signal = Mono.firstWithSignal(emptyEarly, valueLater)
            .defaultIfEmpty("<empty>")
            .block();
        System.out.println("empty/signal=" + signal);

        String value = Mono.firstWithValue(emptyEarly, valueLater)
            .block();
        System.out.println("empty/value=" + value);

        // A lỗi sớm; B vẫn có dữ liệu muộn hơn.
        Mono<String> errorEarly = Mono.<String>error(
                new IllegalStateException("down"))
            .delaySubscription(Duration.ofMillis(20));
        Mono<String> healthy = Mono.just("healthy")
            .delayElement(Duration.ofMillis(80));

        String errorSignal = Mono.firstWithSignal(errorEarly, healthy)
            .onErrorResume(ex -> Mono.just(
                ex.getClass().getSimpleName() + ":" + ex.getMessage()))
            .block();
        System.out.println("error/signal=" + errorSignal);

        String valueDespiteError = Mono.firstWithValue(errorEarly, healthy)
            .block();
        System.out.println("error/value=" + valueDespiteError);

        // Winner Flux tiếp tục phát mọi phần tử của chính nó.
        Flux<String> slow = Flux.just("slow-1", "slow-2")
            .delayElements(Duration.ofMillis(150));
        Flux<String> fast = Flux.just("fast-1", "fast-2")
            .delayElements(Duration.ofMillis(40));
        List<String> stream = Flux.firstWithValue(slow, fast)
            .collectList()
            .block();
        System.out.println("flux=" + stream);

        // Tất cả ứng viên không phát được giá trị.
        Mono<String> noValue = Mono.firstWithValue(
            Mono.<String>empty(),
            Mono.<String>error(new IllegalArgumentException("failed")));
        try {
            noValue.block();
        } catch (NoSuchElementException ex) {
            int causeCount = Exceptions.unwrapMultiple(
                ex.getCause()).size();
            System.out.println("noValue=" +
                ex.getClass().getSimpleName() + ";causes=" + causeCount);
        }
    }
}
~~~

**Lý giải:** firstWithSignal nhận onComplete rỗng trước nên dùng defaultIfEmpty để in tên trạng thái; firstWithValue bỏ qua empty và chọn OK. Với lỗi sớm, firstWithSignal giữ lỗi (onErrorResume chỉ để demo cách in), firstWithValue chờ healthy. Với Flux, fast phát fast-1 trước và tiếp tục fast-2; dữ liệu slow bị hủy. Khi hai nguồn không có giá trị, NoSuchElementException có cause gộp hai nguồn.

**block() ở đây chỉ dùng tại điểm cuối chương trình CLI** để chờ stdout theo thứ tự. Trong WebFlux controller/service, không được gọi block() trên event-loop; trả Mono/Flux cho framework quản lý subscription.

### 8.4. Chạy và stdout

Máy cần JDK 17+, Maven và có thể tải dependency Maven Central.

~~~bash
java -version
mvn -version
mvn test
mvn -q exec:java -Dexec.mainClass=com.example.race.RaceDemo
~~~

**Dòng stdout do main in ra** (không kể log của Maven):

~~~text
empty/signal=<empty>
empty/value=OK
error/signal=IllegalStateException:down
error/value=healthy
flux=[fast-1, fast-2]
noValue=NoSuchElementException;causes=2
~~~

Các giá trị và thứ tự được thiết kế từ độ trễ khác nhau. Lịch phát thực tế vẫn có thể ảnh hưởng bởi tải máy; dùng kiểm thử **virtual time** để chứng minh hành vi thời gian một cách ổn định.

## 9. Kiểm thử với StepVerifier.withVirtualTime

Với operator race, test quan trọng là **tín hiệu nào xuất hiện trước**, không phải code chạy sau bao nhiêu mili-giây trên máy. **StepVerifier.withVirtualTime** cài scheduler thời gian ảo trước khi dựng Publisher trong lambda; thenAwait tiến đồng hồ tức thời, expectNext/verifyComplete/expectError kiểm tra chính xác tín hiệu.

**src/test/java/com/example/race/RaceTest.java**

~~~java
package com.example.race;

import java.time.Duration;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

class RaceTest {

    @Test
    void emptyCompletionWinsFirstWithSignal() {
        StepVerifier.withVirtualTime(() -> Mono.firstWithSignal(
                Mono.<String>empty()
                    .delaySubscription(Duration.ofSeconds(1)),
                Mono.just("OK")
                    .delayElement(Duration.ofSeconds(3))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .verifyComplete();
    }

    @Test
    void firstWithValueWaitsForValueDespiteEarlyEmpty() {
        StepVerifier.withVirtualTime(() -> Mono.firstWithValue(
                Mono.<String>empty()
                    .delaySubscription(Duration.ofSeconds(1)),
                Mono.just("OK")
                    .delayElement(Duration.ofSeconds(3))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectNext("OK")
            .verifyComplete();
    }

    @Test
    void fastErrorWinsFirstWithSignal() {
        StepVerifier.withVirtualTime(() -> Mono.firstWithSignal(
                Mono.<String>error(new IllegalStateException("down"))
                    .delaySubscription(Duration.ofSeconds(1)),
                Mono.just("OK")
                    .delayElement(Duration.ofSeconds(3))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .expectErrorMatches(ex ->
                ex instanceof IllegalStateException &&
                "down".equals(ex.getMessage()))
            .verify();
    }

    @Test
    void firstWithValueCanIgnoreEarlyError() {
        StepVerifier.withVirtualTime(() -> Mono.firstWithValue(
                Mono.<String>error(new IllegalStateException("down"))
                    .delaySubscription(Duration.ofSeconds(1)),
                Mono.just("OK")
                    .delayElement(Duration.ofSeconds(3))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectNext("OK")
            .verifyComplete();
    }

    @Test
    void allSourcesWithoutValueProduceCompositeFailure() {
        StepVerifier.withVirtualTime(() -> Mono.firstWithValue(
                Mono.<String>empty()
                    .delaySubscription(Duration.ofSeconds(1)),
                Mono.<String>error(new IllegalStateException("down"))
                    .delaySubscription(Duration.ofSeconds(2))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectError(NoSuchElementException.class)
            .verify();
    }

    @Test
    void fluxWinnerEmitsAllItsValues() {
        StepVerifier.withVirtualTime(() -> Flux.firstWithValue(
                Flux.just("slow-1", "slow-2")
                    .delayElements(Duration.ofSeconds(3)),
                Flux.just("fast-1", "fast-2")
                    .delayElements(Duration.ofSeconds(1))))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectNext("fast-1", "fast-2")
            .verifyComplete();
    }

    @Test
    void loserIsCancelled() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.withVirtualTime(() -> {
                Mono<String> slow = Mono.just("slow")
                    .delayElement(Duration.ofSeconds(5))
                    .doOnCancel(() -> cancelled.set(true));
                Mono<String> fast = Mono.just("fast")
                    .delayElement(Duration.ofSeconds(1));
                return Mono.firstWithValue(slow, fast);
            })
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("fast")
            .verifyComplete();

        assertTrue(cancelled.get());
    }
}
~~~

Đây là test đơn vị theo thời gian ảo, không cần chạy web server hoặc chờ 3–5 giây thật. Hai test đầu chứng minh khác nhau giữa tín hiệu và giá trị trên **cùng input**. Hai test tiếp theo xác nhận hành vi đối với lỗi sớm. Test Flux giữ toàn bộ sequence winner; test cancellation kiểm tra tín hiệu hủy nguồn thua đã đăng ký.

**Quy tắc viết test:**
- Tạo Mono/Flux bên **trong supplier** của withVirtualTime. Nếu tạo ở ngoài rồi truyền vào, Scheduler thực có thể đã bị giữ lại, làm virtual time không chi phối.
- Gọi expectSubscription trước expectNoEvent nếu dùng; subscription cũng được tính là event.
- Dùng thenAwait để tiến clock; với nguồn vô hạn thêm take(n) hoặc thenCancel, đừng đợi verifyComplete không bao giờ tới.
- Không kiểm tra ai thắng khi cả hai phát **chính xác cùng một mốc** rồi mặc định nguồn đầu tiên thắng. Hãy tách mốc 1s và 3s, hoặc chỉ assert bất biến nghiệp vụ trong race tie.
- Cancellation chỉ nói về subscription được hủy; không khẳng định mọi request từ nguồn thua chưa đến remote.

### 9.1. Kiểm tra composite cause cụ thể

Fragment sau đặt **trong một test method** (cần imports của JUnit/StepVerifier tương ứng):

~~~java
StepVerifier.create(Mono.firstWithValue(
        Mono.<String>empty(),
        Mono.<String>error(new IllegalStateException("db-down"))))
    .expectErrorSatisfies(ex -> {
        org.junit.jupiter.api.Assertions.assertTrue(
            ex instanceof NoSuchElementException);
        Throwable cause = ex.getCause();
        org.junit.jupiter.api.Assertions.assertNotNull(cause);

        java.util.List<Throwable> details =
            reactor.core.Exceptions.unwrapMultiple(cause);
        org.junit.jupiter.api.Assertions.assertEquals(2, details.size());
        org.junit.jupiter.api.Assertions.assertTrue(
            details.get(0) instanceof NoSuchElementException);
        org.junit.jupiter.api.Assertions.assertTrue(
            details.get(1) instanceof IllegalStateException);
    })
    .verify();
~~~

Danh sách cause được mô tả theo thứ tự nguồn; ghi nhận tên vùng gắn với index khi debug. **Đừng đưa composite exception nguyên bản ra HTTP response** vì có thể làm lộ tên backend/stack trace. Lớp biên cần phân loại lỗi nghiệp vụ và ghi metric/log thích hợp.

## 10. Ví dụ ứng dụng Spring WebFlux: đọc hai replica

Giả sử có hai HTTP endpoint trả cùng loại **Profile**; yêu cầu đọc từ vùng nào **có giá trị trước**. Có thể dùng WebClient không blocking và Mono.firstWithValue. Nếu 404 là “không có profile”, phải chuyển 404 thành Mono.empty() ở **từng nguồn**, trước khi đưa vào race; WebClient.retrieve() mặc định thường chuyển 4xx/5xx thành lỗi. Nếu một vùng trả 500 nhưng vùng khác trả profile, firstWithValue có thể chọn profile.

Ví dụ dưới đây là **fragment controller để tích hợp vào Spring Boot WebFlux**, cần ứng dụng Spring Boot, dependency spring-boot-starter-webflux, bean WebClient.Builder và cấu hình URL cho môi trường thật:

~~~java
package com.example.web;

import java.time.Duration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/profiles")
public class ProfileController {
    public record Profile(String id, String displayName) {}

    private final WebClient east;
    private final WebClient west;

    public ProfileController(WebClient.Builder builder) {
        this.east = builder.clone()
            .baseUrl("https://east.example.internal").build();
        this.west = builder.clone()
            .baseUrl("https://west.example.internal").build();
    }

    private Mono<Profile> lookup(WebClient client, String id) {
        return client.get()
            .uri("/profiles/{id}", id)
            .exchangeToMono(response -> {
                if (response.statusCode().value() == 404) {
                    return Mono.empty();
                }
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(Profile.class);
                }
                return response.createError();
            })
            .timeout(Duration.ofSeconds(2));
    }

    @GetMapping("/{id}")
    public Mono<Profile> get(@PathVariable String id) {
        Mono<Profile> a = lookup(east, id);
        Mono<Profile> b = lookup(west, id);

        return Mono.firstWithValue(a, b)
            .timeout(Duration.ofSeconds(3));
    }
}
~~~

**Vì sao dùng exchangeToMono?** Chúng ta phân loại response rõ ràng: HTTP 404 trở thành Mono.empty(), 2xx decode body, còn lỗi khác trở thành tín hiệu onError; phương thức WebClient quản lý tiêu thụ/giải phóng body theo callback. Không lầm rằng onStatus(..., response -> Mono.empty()) ở retrieve tự động làm cả body của response 404 trở thành Mono.empty(); nó chỉ bỏ qua việc tạo exception tương ứng.

**Giới hạn thiết kế:**
- **Cả hai replica có thể được gọi.** Race tiêu thụ tối đa hai request HTTP cho một request người dùng; phải có connection pool, rate limit và ngân sách tải hợp lý.
- **Cancel loser không hoàn tác request phía server.** Chỉ áp dụng cho đọc/idempotent, tránh gây ghi lặp.
- **Nguồn nhanh nhất có thể chứa dữ liệu cũ.** Nếu cần consistency, kiểm tra phiên bản, timestamp hoặc nguồn có thẩm quyền. firstWithValue không có cơ chế chọn bản mới nhất.
- **Nếu cả hai trả 404 hoặc lỗi**, firstWithValue từ hai nguồn có thể báo NoSuchElementException với cause composite, **không tự trả 404**. Ánh xạ 404/503/timeout tùy chính sách và cause: hai nguồn cùng 404 khác với một 404 và một 500.
- **Nếu một vùng là never/hung**, timeout từng nguồn và deadline tổng cho phép tránh chờ mãi.
- **Nếu request bị hủy**, cần quan sát hủy I/O, metric theo vùng, trace context và connection leak; không tự gọi subscribe trong controller.
- **Bảo mật:** xác thực, phân quyền, TLS, không log token/bí mật, giới hạn truy vấn và truyền Reactor Context theo cơ chế framework.

**Không dùng firstWithValue nếu mọi yêu cầu đọc buộc phải trả kết quả từ một source of truth.** Khi tính nhất quán mạnh quan trọng hơn tail latency, chọn kiến trúc dữ liệu phù hợp thay vì mặc định đua.

## 11. Tình huống thực hành để chọn toán tử

### 11.1. Cache miss nhanh

Cache trả Mono.empty() ở 10ms, DB trả profile ở 90ms:
- **firstWithSignal(cache, db):** cache empty thắng, client không thấy profile.
- **firstWithValue(cache, db):** DB có giá trị thắng, nhưng DB thường được gọi ngay cả khi cache có dữ liệu.
- **cache.switchIfEmpty(Mono.defer(dbQuery)):** dùng DB khi cache miss, giảm tải khi cache hit. Với cache thường trúng và DB đắt, đây thường là thiết kế phù hợp.

### 11.2. Lỗi nhanh ở một vùng

Region A lỗi mạng sau 20ms, region B trả profile ở 120ms:
- **firstWithSignal:** trả lỗi A ở 20ms.
- **firstWithValue:** B trả profile ở 120ms.
- **onErrorResume:** có thể chuyển A sang B **tuần tự**; phù hợp nếu chỉ muốn gọi B khi A thực sự lỗi, tránh 2 request đồng thời.

### 11.3. Stream thắng rồi lỗi về sau

Flux A phát A1 ở 10ms rồi onError ở 100ms. Flux B phát B1 ở 50ms rồi phát liên tục:
- **firstWithValue:** A đã thắng ở A1, nên downstream nhận A1 rồi **onError của A**, không tự động lấy B.
- **firstWithSignal:** A cũng thắng theo onNext A1.
- Nếu muốn chuyển nguồn sau khi A lỗi, cần định nghĩa **khôi phục từng giai đoạn** (resume/switch) và xử lý dữ liệu trùng, thứ tự và replay; không kỳ vọng một cuộc đua ban đầu làm điều đó.

### 11.4. Hai nguồn không trả dữ liệu

A rỗng, B lỗi, C không phát bất cứ thứ gì:
- **firstWithSignal:** một onComplete/onError đến sớm có thể thắng.
- **firstWithValue:** chờ C nếu vẫn chưa có giá trị; cần timeout. Khi cả ba đều kết thúc không có giá trị, lỗi tổng hợp chứa nguyên nhân của từng nguồn.

### 11.5. Cần cả dữ liệu A và B

Nếu yêu cầu **phải có cả kết quả thanh toán và số điểm tích lũy**, không dùng race vì mất một nguồn. Dùng zip khi cần cả hai; dùng merge nếu cần tất cả sự kiện và chấp nhận đan xen; dùng concat khi cần hoàn tất A rồi mới B.

## 12. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi firstWithSignal là lấy giá trị nhanh nhất | Empty/error sớm có thể thắng | Dùng firstWithValue khi cần onNext đầu tiên. |
| Coi Mono.empty() là null | Hiểu sai signal và fallback | Empty là onComplete không có onNext; không dùng Mono.just(null). |
| Coi firstWithValue luôn thành công | Khi không nguồn nào có giá trị, xảy ra NoSuchElementException | Kiểm tra composite cause và ánh xạ lỗi theo domain. |
| Hiểu firstWithValue chỉ lấy một phần tử Flux | Bỏ qua các giá trị sau của winner | Winner tiếp tục phát cả sequence; dùng next() nếu cần 1 phần tử. |
| Cho rằng winner lỗi sau thì tự chọn loser | Pipeline kết thúc bằng lỗi thắng | Thiết kế onErrorResume/failover rõ riêng. |
| Cho rằng loser bị cancel nghĩa là request chưa chạy | Có thể đã commit/đã gửi email | Race đọc/idempotent; xử lý side effect đúng. |
| Race DB và cache dù chỉ cần fallback | Tăng số request DB | switchIfEmpty để fallback tuần tự khi phù hợp. |
| Không đặt timeout | firstWithValue có thể đợi Mono.never | Đặt deadline toàn request và timeout từng nguồn. |
| Trả 404 khi gặp mọi NoSuchElementException | Che giấu lỗi vùng không sẵn sàng | Phân loại cause composite: 404 khác 503. |
| Test bằng sleep và dự đoán tie | Test flake theo CPU/scheduler | Virtual time với các mốc rõ ràng, không khẳng định winner khi tie. |
| Dùng race thay cho zip | Không có đủ dữ liệu để tổng hợp | Nếu cần cả hai, dùng zip thay vì chọn winner. |
| Tin nguồn nhanh nhất là bản mới nhất | Trả dữ liệu cũ | Kiểm tra consistency, version và quy tắc freshness. |

## 13. Bài tập với gợi ý đáp án

**Bài 1: So sánh signal với value.** A hoàn thành rỗng sau 1s; B trả "OK" sau 3s. Hãy viết hai StepVerifier.withVirtualTime: firstWithSignal hoàn thành rỗng ở 1s; firstWithValue trả OK ở 3s. **Gợi ý:** delaySubscription trên Mono.empty và delayElement trên Mono.just.

**Bài 2: Nguồn lỗi nhanh.** A lỗi IllegalStateException ở 500ms, B trả "OK" ở 2s. Dự đoán firstWithSignal trả lỗi A, firstWithValue trả OK. Dùng expectErrorMatches để kiểm tra lỗi gốc; đừng dùng onErrorResume trong test nếu mục đích là chứng minh lỗi.

**Bài 3: Lỗi gộp.** A rỗng, B lỗi IllegalArgumentException. Dùng StepVerifier.expectErrorSatisfies, kiểm tra NoSuchElementException và Exceptions.unwrapMultiple(...).size() = 2. Giải thích vì sao không thể trả HTTP 404 cho cả hai trường hợp nếu một vùng thật sự lỗi 500.

**Bài 4: Flux winner.** A phát A1/A2 sau mỗi 3s; B phát B1/B2 sau mỗi 1s. Đáp án dự kiến là B1, B2 rồi complete. Test với virtual time và dùng doOnCancel xác nhận A bị hủy.

**Bài 5: Chọn mô hình fallback.** Cache hit 95%, DB tốn chi phí cao: nên dùng switchIfEmpty tuần tự hoặc firstWithValue race? Tính đến tail latency, lưu lượng DB, độ mới dữ liệu và khả năng của pool; đưa ra lý do, không chỉ chọn theo tên operator.

## 14. Checklist trước khi triển khai

- [ ] Nêu rõ yêu cầu là **tín hiệu đầu tiên** hay **giá trị đầu tiên**.
- [ ] Có test cho A rỗng trước, A lỗi trước, A có dữ liệu trước và tất cả nguồn không có giá trị.
- [ ] Với Flux, hiểu winner giữ toàn bộ phần còn lại; loser bị cancel nếu đã subscribe.
- [ ] Đã chọn số lượng đối thủ tối đa, timeout, retry có giới hạn và ngân sách connection.
- [ ] Không đua tác vụ ghi không idempotent; cancel không hoàn tác side effect.
- [ ] Phân loại NoSuchElementException composite và chuẩn hóa mã lỗi HTTP.
- [ ] Dùng VirtualTimeScheduler/StepVerifier cho race theo thời gian; không giả định tie.
- [ ] Đã so sánh với switchIfEmpty/onErrorResume/zip/merge/concat trước khi chọn race.
- [ ] Đã xác định yêu cầu consistency/freshness nếu dữ liệu từ nhiều replica.
- [ ] Trong WebFlux, trả Mono/Flux cho framework; không gọi block hoặc subscribe tự phát trong request path.

## 15. Tài liệu tham khảo

1. Reactor Core Mono Javadoc – firstWithSignal, firstWithValue: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
2. Reactor Core Flux Javadoc – firstWithSignal, firstWithValue: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
3. Reactor Core Exceptions Javadoc – unwrapMultiple: https://projectreactor.io/docs/core/release/api/reactor/core/Exceptions.html
4. Reactor Test StepVerifier – withVirtualTime và kiểm tra tín hiệu: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
5. Project Reactor Reference Guide – lỗi, cancellation, testing: https://projectreactor.io/docs/core/release/reference/
6. Spring Framework WebFlux – Publisher và WebClient: https://docs.spring.io/spring-framework/reference/web/webflux.html

**Tự đánh giá:** Nếu giải thích được vì sao một Mono.empty() có thể thắng firstWithSignal nhưng không thắng firstWithValue, vì sao firstWithValue có lỗi composite khi mọi nguồn thiếu giá trị, và vì sao Flux winner tiếp tục phát các phần tử sau, bạn đã nắm được hai toán tử race cốt lõi.
