# Java Console: char[] và quản lý vòng đời dữ liệu nhạy cảm

## Mục tiêu học tập

Khi một chương trình Java dòng lệnh cần nhận **mật khẩu, passphrase, PIN hoặc chuỗi bí mật**, thiết kế luồng dữ liệu quan trọng không kém việc tắt hiển thị ký tự lúc nhập. **java.io.Console.readPassword(...)** trả về **char[]** để ứng dụng có thể chủ động ghi đè vùng nhớ chứa ký tự sau khi dùng xong. Tuy nhiên, **char[] không tự làm bí mật trở nên an toàn**: quản lý quyền sở hữu, bản sao, các API nhận dữ liệu, lỗi ngoại lệ và thời điểm xóa đều phải được thiết kế rõ.

Bài học tập trung vào chủ đề **char[] và quản lý vòng đời dữ liệu nhạy cảm** trong ngữ cảnh **Console**, với API hiện hành trên JDK 17 trở lên. Sau bài này, bạn sẽ biết:

1. Khi nào dùng **Console.readPassword()** thay cho **readLine()**, và cách ứng xử khi không có console hoặc người dùng gửi EOF.
2. Tại sao **String** và **char[]** có đặc tính quản lý bộ nhớ khác nhau, nhưng không được coi việc dùng char[] là bảo đảm xóa sạch mọi dấu vết.
3. Định nghĩa **vòng đời dữ liệu**: tiếp nhận → sở hữu → xử lý → truyền qua ranh giới API → dọn dẹp → kiểm thử.
4. Xóa mảng trong **finally** bằng **Arrays.fill(...)**, kể cả khi bước xử lý ném exception.
5. Nhận biết những bản sao ngoài ý muốn do **new String(...), String.valueOf(...), Arrays.copyOf(...), clone(), encoding, các thư viện và logging**.
6. Phân biệt việc xóa dữ liệu khỏi một mảng Java với các yêu cầu bảo mật khác như quyền truy cập, hệ thống lưu trữ bí mật, chống rò rỉ log và xác thực mật khẩu thực sự.
7. Biên dịch/chạy ví dụ Java 17+ độc lập, tự kiểm tra việc xóa trên hai nhánh thành công/lỗi mà không sử dụng mật khẩu thật.

**Nguyên tắc cốt lõi:** Giữ bí mật trong bộ nhớ **ít nơi nhất, thời gian ngắn nhất, dưới quyền kiểm soát rõ ràng**, sau đó xóa những buffer mà chương trình thực sự sở hữu được. Đây là biện pháp **giảm rủi ro**, không phải lời hứa rằng JVM hoặc hệ điều hành sẽ không còn bất kỳ bản sao nào.

## 1. Tại sao vấn đề không dừng ở việc ẩn ký tự nhập?

Hãy hình dung một CLI đăng nhập:

~~~text
Người dùng nhập trên terminal
            │
            ▼
Console.readPassword(...) ──> char[] do chương trình nhận
            │                           │
            │                           ├── không echo ký tự trên console
            │                           ├── có thể xử lý qua API nhận char[]
            │                           └── Arrays.fill sau khi không còn cần
            │
            ▼
       Một bước xử lý
            │
            ├── thành công: dọn mảng
            └── lỗi/exception: vẫn dọn mảng trong finally
~~~

Nếu ứng dụng **in ra mật khẩu**, lưu vào **String**, ghi vào **log**, truyền vào **command-line argument** của tiến trình khác hoặc giữ trong một field lâu dài, việc tắt echo khi nhập không giải quyết được những đường rò rỉ đó.

Ngược lại, một ứng dụng vẫn có thể bị truy cập dữ liệu trong heap dump, memory snapshot, log của thư viện hoặc qua tiến trình có quyền cao hơn, dù nó dùng char[] và dọn mảng đúng cách.

### 1.1. Một mô hình rủi ro đơn giản

| Rủi ro | Ví dụ | Biện pháp giảm thiểu |
| --- | --- | --- |
| Lộ ký tự khi nhập | Người đứng cạnh nhìn được terminal khi dùng readLine | Dùng **Console.readPassword(...)** khi có console tương tác phù hợp |
| Lộ qua output/log | **System.out.println(password)** | Tuyệt đối không in dữ liệu, kể cả ở log debug/test |
| Lưu quá lâu trong heap | Giữ mật khẩu trong String/field/cache | Giữ trong vùng nhớ có thể xóa, giới hạn phạm vi sử dụng, clear sớm |
| Bản sao ngoài ý muốn | new String(password), mảng clone, mã hóa byte[] | Tránh copy; quản lý và dọn từng bản sao có thể kiểm soát |
| Không dọn khi lỗi | Xử lý ném exception trước lệnh Arrays.fill | Dùng **try/finally**, đặt cleanup tại chủ sở hữu |
| Không có console thật | IDE, CI, input bị redirect hoặc EOF | Xử lý **null**/EOF tường minh; không tự đọc bằng readLine |
| Dữ liệu bị lộ bên ngoài JVM | Heap dump, process memory, môi trường không cô lập | Hạn chế quyền, cấu hình vận hành, rút ngắn vòng đời, cơ chế bảo mật tổng thể |

Mỗi rủi ro có cơ chế khác nhau. **char[]** chỉ giải quyết được một phần cụ thể: cho phép ứng dụng chủ động **ghi đè các phần tử trong mảng mà nó còn truy cập**.

## 2. Console.readPassword(...) trả về gì?

Lớp **java.io.Console** thuộc **java.base**. Một chương trình Java có thể lấy Console bằng:

~~~java
// Mảnh mã minh họa, không phải chương trình độc lập.
Console console = System.console();
if (console == null) {
    // Không có console phù hợp trong môi trường hiện tại.
    return;
}
char[] password = console.readPassword("Enter secret: ");
~~~

Những điều cần biết:

- **Console.readPassword()** và **Console.readPassword(String, Object...)** đọc một dòng ký tự, **tắt echo** trong quá trình nhập, và trả **char[]** không chứa ký tự kết thúc dòng.
- Giá trị có thể là **null nếu đầu vào đã kết thúc (EOF)**. Đây không phải một mảng rỗng và không nên được truyền tiếp như mật khẩu.
- **readPassword** có thể gây **IOError** khi gặp lỗi I/O. Nếu dùng phiên bản có định dạng prompt, các lỗi định dạng cũng có thể xuất hiện theo hợp đồng API.
- **System.console()** có thể trả **null** khi không có console phù hợp; thường gặp khi chạy trong IDE, CI hoặc một môi trường không có terminal theo cách JVM hỗ trợ.
- Ngược lại, một số môi trường/JDK có thể trả **Console khác null** dù đầu vào không tương tác như bạn nghĩ. **Console khác null không bảo đảm người dùng sẽ nhập dữ liệu**; vẫn phải xử lý trường hợp **readPassword(...) trả null** vì EOF.
- Không nên tự động fallback sang **Scanner.nextLine()**, **BufferedReader.readLine()** hoặc **Console.readLine()** để nhận secret nếu yêu cầu của sản phẩm là nhập không hiển thị và quản lý bằng char[].

Tùy cách host kết nối luồng stdin/stdout, prompt có thể hiện lên rồi gặp EOF. Ví dụ test không tương tác ở phần 7 đã quan sát điều này trên JDK 24 và xử lý bằng cách **dừng an toàn**, không coi EOF là một mật khẩu hợp lệ.

### 2.1. Phân biệt readLine và readPassword

| Tiêu chí | **Console.readLine(...)** | **Console.readPassword(...)** |
| --- | --- | --- |
| Giá trị trả về | **String** | **char[]** |
| Echo ký tự khi nhập | Có, theo hành vi đọc dòng tương tác | Không echo theo contract của API |
| Chủ động ghi đè ký tự sau khi dùng | Không thể thay đổi nội dung String bằng API công khai | Có thể dùng **Arrays.fill** trên mảng trả về |
| Phù hợp cho | Tên đăng nhập, lựa chọn menu, văn bản không nhạy cảm | Mật khẩu, passphrase và bí mật nhập trực tiếp |
| Trường hợp EOF | Có thể trả **null** | Có thể trả **null** |

**Đừng nhầm tắt echo với mã hóa hoặc bảo vệ đầu cuối.** Tính năng này chỉ tác động cách console hiển thị ký tự trong khi nhập. Nó không tự bảo vệ clipboard, màn hình ghi hình, input từ nguồn không tin cậy, bộ nhớ JVM hoặc hệ thống lưu trữ đích.

### 2.2. Vì sao không nên dùng các cách đọc thay thế?

~~~java
// KHÔNG NÊN dùng cho bí mật: tạo String khó xóa.
String secret = console.readLine("Password: ");
~~~

Đây là mảnh code **để nhận diện lỗi**, không phải cách làm được khuyến nghị. **String** là immutable và không cung cấp API để ghi đè nội dung. Một String chứa bí mật có thể còn tồn tại trong bộ nhớ cho đến khi JVM quản lý thu gom và tái sử dụng vùng nhớ; thời điểm đó không do ứng dụng kiểm soát.

Nếu một môi trường không hỗ trợ console nhập không echo, giải pháp đúng phụ thuộc sản phẩm: từ chối tương tác, dùng UI có thành phần nhập nhạy cảm, một secure input abstraction được kiểm tra, hoặc tích hợp **secret manager** với chính sách bảo mật phù hợp. Không âm thầm giảm tiêu chuẩn an toàn chỉ để chương trình tiếp tục chạy.

## 3. String và char[]: khác nhau thế nào?

Một so sánh thực tế:

| Đặc điểm | String | char[] |
| --- | --- | --- |
| Mutability | Immutable | Có thể thay đổi từng phần tử |
| Lệnh dọn trực tiếp nội dung | Không có API công khai để xóa ký tự đã tạo | **Arrays.fill(array, '\0')** |
| Chia sẻ tham chiếu | Có thể có nhiều tham chiếu cùng String | Có thể có nhiều tham chiếu cùng mảng |
| Copy và lưu dấu vết | Các thao tác chuyển đổi có thể tạo object khác | **clone**, **copyOf**, encoding cũng có thể tạo bản sao |
| Bảo đảm xóa toàn bộ bí mật khỏi process | Không | **Cũng không** |
| Phù hợp cho bí mật ngắn hạn nhập qua Console | Không ưu tiên | **Nên ưu tiên nếu các API tiếp theo cho phép** |

Điểm then chốt không nằm ở việc **String bị coi là sai trong mọi trường hợp**. Nhiều API/JDK/framework dùng String như kiểu dữ liệu bắt buộc. Điều quan trọng là biết lúc nào **không thể tránh bản sao String**, ghi nhận giới hạn đó và **không cố tuyên bố cleanup tuyệt đối** khi đã mất quyền kiểm soát dữ liệu.

### 3.1. Chuyển char[] thành String là một ranh giới mới

Những lời gọi dưới đây có thể tạo một bản String chứa dữ liệu nhạy cảm:

~~~java
// Chỉ minh họa những thao tác cần tránh cho secret.
String copy1 = new String(password);
String copy2 = String.valueOf(password);
~~~

**Xóa password bằng Arrays.fill sau đó không xóa được nội dung của copy1/copy2**. Những object này không thể được zeroize bằng API String công khai.

Vì vậy, tránh chuyển đổi chỉ để tiện so sánh, trim, log, truyền qua JSON hoặc gọi một helper vốn không cần String. Nếu thư viện thực sự chỉ chấp nhận String, hạn chế thời gian giữ tham chiếu, không cache/log, chọn thư viện có giao diện phù hợp hơn nếu khả thi, và hiểu rủi ro phần bộ nhớ không chủ động xóa được.

### 3.2. Một mảng cũng có thể có nhiều bản sao

~~~java
// Mảnh minh họa: hai vùng nhớ khác nhau.
char[] original = {'a', 'b'};
char[] copy = original.clone();

Arrays.fill(original, '\0'); // Chỉ xóa original.
Arrays.fill(copy, '\0');     // Phải xóa cả bản sao.
~~~

Tương tự, **Arrays.copyOf(password, password.length)** tạo một array mới. Mỗi buffer do chương trình tạo cần có chủ sở hữu và kế hoạch cleanup riêng. **Arrays.fill** không tìm và xóa bản sao đã được đưa sang thư viện, thread, cache, log hoặc môi trường khác.

### 3.3. Chỉ làm biến tham chiếu bằng null chưa đủ

~~~java
// Không tương đương với dọn ký tự đã lưu trong array.
password = null;
~~~

Việc gán **null** chỉ bỏ một tham chiếu. Nếu object vẫn còn tham chiếu khác, vùng nhớ tiếp tục chứa nội dung; kể cả khi không còn tham chiếu, không có cam kết JVM sẽ xóa byte ngay lập tức. Khi bạn còn quyền truy cập array, hãy **ghi đè các phần tử** trước khi để object không còn được dùng.

## 4. Vòng đời dữ liệu nhạy cảm: từ lúc nhập đến khi giải phóng

Một quy trình được thiết kế tốt không chỉ có hai dòng đọc và xóa. Nên xét đầy đủ:

~~~text
Acquire
  ↓ char[] từ Console.readPassword()
Validate availability
  ↓ null/EOF? → dừng an toàn
Assign ownership
  ↓ ai chịu trách nhiệm dọn mảng?
Use briefly
  ↓ helper/API nhận char[], không giữ tham chiếu
Handle failures
  ↓ mọi đường thoát đều qua finally
Clear owned buffers
  ↓ Arrays.fill với '\0'
Release references
  ↓ không đưa vào field/cache/async/log
Complete
~~~

### 4.1. Tiếp nhận (Acquire)

Nguồn input có thể là terminal, giao diện đồ họa hoặc secret manager. **Console.readPassword** phù hợp với CLI tương tác thực sự. Nó trả array mà caller phải coi là nhạy cảm kể từ khi nhận được.

Nếu **null** vì EOF, không có char[] để xóa. Nếu mảng có độ dài 0, đó là **đầu vào rỗng**, không đồng nghĩa EOF. Ứng dụng quyết định có chấp nhận đầu vào rỗng hay không theo nghiệp vụ; một chương trình xác thực thường phải có kiểm tra phù hợp, thay vì giả định mảng rỗng hợp lệ.

### 4.2. Quyền sở hữu (Ownership)

Quy tắc rõ nhất là: **hàm hoặc thành phần nhận quyền sở hữu char[] có trách nhiệm xóa mảng khi kết thúc công việc**.

Trong ví dụ của bài, helper **useThenClear(...)** nhận quyền sở hữu mảng. Contract cho người gọi:

- Không tiếp tục dùng array sau khi helper trả về.
- Không truyền array đó đồng thời cho code khác đang còn sử dụng.
- Không giữ nó trong field, lambda tồn tại lâu, Future, queue hoặc cache.
- Nếu thật sự cần tạo bản sao, định nghĩa chủ sở hữu và cleanup cho từng bản.
- Không để consumer trả lại chính reference char[] hoặc lưu reference đó ra ngoài phạm vi. Java type system không tự chặn vi phạm này.

Đây là **quy ước ở cấp ứng dụng**, không phải cơ chế compiler tự thực thi.

### 4.3. Xử lý (Use)

Một bước xử lý có thể xác minh định dạng, truyền cho một API phù hợp hoặc khởi tạo công cụ nhận char[]. **Không giữ secret lâu hơn cần thiết chỉ vì callback chưa hoàn tất**. Với xử lý bất đồng bộ, phải thiết kế lại ownership theo lifecycle bất đồng bộ, không thể tự tiện xóa array ngay sau khi enqueue rồi mong task sau vẫn đọc được.

Nếu thư viện lưu/copy char[], phải đọc contract của thư viện đó: caller xóa bản đầu vào không có nghĩa thư viện đã xóa bản sao của mình.

### 4.4. Dọn dẹp (Cleanup)

Mẫu quan trọng nhất:

~~~java
// Mảnh minh họa độc lập về control flow.
char[] secret = acquireSecretSomehow();
try {
    processSecret(secret);
} finally {
    Arrays.fill(secret, '\0');
}
~~~

**acquireSecretSomehow()** và **processSecret(...)** là các hàm đại diện cho nghiệp vụ, không phải API Java, nên đoạn trên **chỉ minh họa**. Trong chương trình thực, phải kiểm tra **null** trước khi gọi **Arrays.fill**, và lựa chọn cleanup phù hợp với bên sở hữu.

**finally** chạy trong đường thực thi bình thường khi thoát khỏi khối try, kể cả khi có exception. Có những tình huống bất thường như JVM/process bị kết thúc đột ngột mà bạn không thể bảo đảm Java cleanup chạy. Vì vậy đây là **best-effort cleanup trong lifecycle chương trình**, không phải bảo đảm bảo mật tuyệt đối.

### 4.5. Giải phóng và kiểm thử (Release, Verify)

Sau cleanup, tránh giữ reference không cần thiết. Nếu code kiểm thử còn giữ tham chiếu, có thể khẳng định mọi phần tử của **mảng cụ thể đó** đã bằng **'\0'**. Không thể dùng điều này để chứng minh tất cả các bản sao nội bộ ở JVM, hệ điều hành và thư viện đã được xóa.

Kiểm thử nên bao gồm nhánh thành công, exception, EOF, thiếu console và không lộ ký tự qua logs/stdout. Đừng dùng mật khẩu thật làm dữ liệu test.

## 5. Vì sao Arrays.fill trong finally là trọng tâm?

**java.util.Arrays.fill(char[] a, char val)** ghi một giá trị lên mọi phần tử của array được truyền.

~~~java
// Mảnh code được hỗ trợ trên JDK 17+.
Arrays.fill(password, '\0');
~~~

Có thể dùng ký tự không nhạy cảm khác, nhưng trong bài chọn **'\0'** để có thể kiểm tra mảng đã được reset dễ dàng. Dùng đúng array cần dọn, không phải array khác có cùng tên biến.

### 5.1. Cleanup sai vị trí

~~~java
// LỖI THIẾT KẾ: nếu usePassword ném exception,
// lệnh fill phía sau có thể không được thực hiện.
usePassword(password);
Arrays.fill(password, '\0');
~~~

**usePassword(...)** là hàm minh họa, không phải API chuẩn JDK. Cách tổ chức trên không đảm bảo cleanup trên mọi nhánh.

### 5.2. Cleanup đúng vòng đời

~~~java
// Mảnh minh họa; caller phải chắc chắn password khác null.
try {
    usePassword(password);
} finally {
    Arrays.fill(password, '\0');
}
~~~

Nếu cần return từ trong try, finally vẫn được thực thi khi rời khỏi try. Cũng cần xử lý từng bản sao nếu có, không trông đợi một lệnh fill xóa tất cả các vùng nhớ chứa dữ liệu.

### 5.3. Không dọn quá sớm

~~~java
// SAI về logic: callback chưa sử dụng xong nhưng dữ liệu đã bị xóa.
Arrays.fill(password, '\0');
sendForVerification(password);
~~~

Đoạn chỉ minh họa lỗi trình tự. Khi callback cần dùng mảng, phải giữ dữ liệu đến đúng lúc xong, rồi dọn ngay. Không thể vừa cam kết "array đã bị xóa" vừa để một consumer dùng array đó ở thời điểm sau.

## 6. Ví dụ Java 17+ chạy được: đọc an toàn và chứng minh xóa

Tạo **một file duy nhất** tên **SecretInputDemo.java**. Chương trình có hai chế độ:

- **Chế độ tương tác:** Nếu có Console, gọi **readPassword(...)**, kiểm tra EOF và dùng mảng trong callback ngắn, sau đó dọn trong finally. Ví dụ chỉ kiểm tra **có ký tự hay không**, **không thực hiện xác thực**.
- **Chế độ --self-test:** Sử dụng dữ liệu giả nhỏ, kiểm tra array đã bị reset sau xử lý thành công và sau một exception có chủ đích. Không lấy mật khẩu thật, không in secret.

### 6.1. Mã hoàn chỉnh

**SecretInputDemo.java**

~~~java
import java.io.Console;
import java.util.Arrays;
import java.util.Objects;
import java.util.function.Function;

public final class SecretInputDemo {
    private SecretInputDemo() {}

    private static <T> T useThenClear(
            char[] ownedSecret, Function<char[], T> action) {
        Objects.requireNonNull(ownedSecret, "ownedSecret");
        try {
            return Objects.requireNonNull(action, "action").apply(ownedSecret);
        } finally {
            Arrays.fill(ownedSecret, '\0');
        }
    }

    private static boolean isCleared(char[] chars) {
        for (char ch : chars) {
            if (ch != '\0') {
                return false;
            }
        }
        return true;
    }

    private static void selfTest() {
        char[] sample = {'d', 'e', 'm', 'o'};
        boolean processed = useThenClear(sample, chars -> chars.length == 4);
        System.out.println("clear-on-success="
                + (processed && isCleared(sample)));

        char[] failing = {'x'};
        boolean caught = false;
        try {
            useThenClear(failing, chars -> {
                throw new IllegalStateException("intentional test failure");
            });
        } catch (IllegalStateException expected) {
            caught = true;
        }
        System.out.println("clear-on-failure="
                + (caught && isCleared(failing)));
    }

    public static void main(String[] args) {
        if (args.length == 1 && "--self-test".equals(args[0])) {
            selfTest();
            return;
        }
        if (args.length != 0) {
            System.err.println("Unsupported argument.");
            return;
        }

        Console console = System.console();
        if (console == null) {
            System.err.println("No interactive console; input cancelled.");
            return;
        }

        char[] password = console.readPassword("Enter secret: ");
        if (password == null) {
            console.printf("Input ended before data was received.%n");
            return;
        }

        boolean hasCharacters = useThenClear(password,
                chars -> chars.length > 0);
        console.printf(hasCharacters
                ? "Input accepted for demonstration; no authentication performed.%n"
                : "Empty input; no authentication performed.%n");
    }
}
~~~

### 6.2. Lệnh biên dịch và tự kiểm tra

Yêu cầu JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 --release 17 SecretInputDemo.java
java SecretInputDemo --self-test
~~~

**Stdout chính xác của chế độ self-test:**

~~~text
clear-on-success=true
clear-on-failure=true
~~~

Hai dòng này có nghĩa **hai mảng giả mà chương trình sở hữu đã được ghi đè thành '\0'**. Chúng **không** chứng minh rằng JVM không còn bất kỳ bản sao nào ở tầng khác.

Nếu chạy không có tham số trên một terminal tương tác được Console hỗ trợ:

~~~bash
java SecretInputDemo
~~~

Chương trình hiển thị prompt:

~~~text
Enter secret:
~~~

Trong lúc nhập, **readPassword** không echo các ký tự. Nếu bạn nhập một chuỗi không rỗng và kết thúc input thành công, chương trình in:

~~~text
Input accepted for demonstration; no authentication performed.
~~~

Với mảng rỗng, chương trình in **Empty input; no authentication performed.**. Với EOF, nó in **Input ended before data was received.**; còn khi không có Console, nó ghi **No interactive console; input cancelled.** lên stderr và dừng.

**Không dùng mật khẩu thật khi thực hành ví dụ:** nó chỉ minh họa vòng đời mảng, không phải một chương trình login hoặc cơ chế xác thực đã được đánh giá bảo mật.

### 6.3. Trường hợp không tương tác

Trên một số cấu hình, **System.console() == null** và ví dụ dừng trước khi đọc. Tuy nhiên, trong phép thử không tương tác trên OpenJDK 24.0.2, JVM vẫn trả một Console, prompt hiện lên rồi **readPassword() trả null vì EOF**. Chương trình đã xử lý tình huống này bằng cách dừng an toàn.

Đừng viết test dựa vào giả định "chạy từ IDE/CI chắc chắn System.console()==null". Quan trọng là xử lý cả hai nhánh và không biến EOF thành đầu vào hợp lệ.

### 6.4. Kết quả kiểm chứng của đoạn mã

Ví dụ trên đã được biên dịch bằng **javac 24.0.2 --release 17** và chạy thành công. Phép kiểm thử xác nhận:

| Ca | Kỳ vọng | Kết quả |
| --- | --- | --- |
| Callback thành công | Mảng dữ liệu giả được xóa | **clear-on-success=true** |
| Callback ném IllegalStateException | finally vẫn xóa mảng | **clear-on-failure=true** |
| Chạy không tương tác, không có đầu vào | Dừng an toàn, không xử lý mật khẩu rỗng như thành công | **PASS** |

Việc kiểm thử này không nhập một secret có thật và không viết thêm resource/credential xuống filesystem. Mã test được chạy trong thư mục tạm được dọn sau khi kiểm tra.

## 7. Giải thích từng chi tiết của ví dụ

### 7.1. Vì sao dùng Function<char[], T>?

**useThenClear(...)** nhận array đã chuyển quyền sở hữu và một callback xử lý. Nó có thể trả bất cứ kiểu T nào mà không trả về hoặc log nội dung array. Dù callback return hay throw, **finally** vẫn gọi **Arrays.fill**.

Điều này thể hiện ranh giới vòng đời trong một nơi duy nhất:

~~~text
char[] từ Console
     │
     ▼
useThenClear nhận quyền sở hữu
     │
     ├── action xử lý ngắn
     │
     └── finally xóa toàn array
     │
     ▼
chỉ kết quả không nhạy cảm thoát ra
~~~

Ở ví dụ, T là Boolean. Với hệ thống thực tế, callback phải thực sự tuân thủ contract: không trả về char[], không lưu reference ra ngoài và không copy sang vùng khác không quản lý được.

### 7.2. Vì sao Objects.requireNonNull trước try?

**Objects.requireNonNull(ownedSecret)** kiểm tra mảng đầu vào. Nếu không có array thì không có gì để xóa trong helper. **Objects.requireNonNull(action)** được đặt **bên trong try**, nên nếu callback bị thiếu sau khi một array đã được trao quyền sở hữu, finally vẫn chạy và xóa array.

Đây là một chi tiết nhỏ nhưng quan trọng trong những helper có contract cleanup: lỗi lập trình của caller cũng không nên vô tình kéo dài vòng đời một buffer mà helper đã nhận.

### 7.3. Vì sao self-test còn giữ tham chiếu array?

Trong bài test, các biến **sample** và **failing** cố tình còn tham chiếu đến mảng sau lời gọi **useThenClear** để **đo được kết quả xóa**. Code nghiệp vụ bình thường không nên giữ reference chỉ để kiểm tra; sau khi helper trả về, caller coi mảng là đã mất hiệu lực.

Hàm **isCleared(...)** kiểm tra từng char bằng **'\0'**; nó không in nội dung trước khi xóa và không tự tạo String chứa secret.

### 7.4. Nếu callback cố ý giữ hoặc sao chép dữ liệu?

Ví dụ helper không thể ngăn callback làm như sau:

~~~java
// SAI về contract: không nên đưa dữ liệu nhạy cảm vào vùng nhớ mới.
char[] hiddenCopy = Arrays.copyOf(chars, chars.length);
~~~

Mã chỉ là **mảnh minh họa**. Nếu thật sự phải sao chép cho API khác, vùng nhớ **hiddenCopy** cần được quản lý/xóa riêng. Helper vẫn xóa array gốc, nhưng không hề tự xóa hiddenCopy.

### 7.5. Vì sao kiểm tra chars.length không phải authentication?

Kiểm tra "đầu vào có ký tự" chỉ là ví dụ để không phải đưa bất kỳ thông tin xác thực nào vào mã nguồn. **Nó không xác minh danh tính người dùng** và không phải chính sách mật khẩu.

Trong ứng dụng thật, cần dùng một cơ chế xác thực được thiết kế và kiểm chứng phù hợp: thư viện/protocol được tin cậy, kênh truyền được bảo vệ, chính sách xử lý credential, giới hạn retry, và phương pháp lưu trữ/so khớp mật khẩu hiện đại của hệ thống. Không hard-code mật khẩu thử trong code sản phẩm hoặc tự chế phương thức xác thực bằng phép so sánh chuỗi.

## 8. Những cách làm khiến char[] mất tác dụng

### 8.1. In trực tiếp char[] có thể làm lộ bí mật

Một lỗi rất dễ bỏ qua:

~~~java
// NGUY HIỂM: PrintStream có overload println(char[])
// có thể in các ký tự thực sự của mảng.
System.out.println(password);
~~~

Đừng nghĩ Java sẽ luôn in một dạng định danh như **[C@...**. **PrintStream.println(char[])** là một overload có thể in nội dung ký tự. Tương tự, tránh **Arrays.toString(password)**, ghi nội dung char[] vào logger, metrics, stack trace, crash report hoặc thông báo exception.

**Quy tắc:** Không đưa secret vào bất kỳ output/log nào. Khi cần audit, chỉ ghi metadata không nhạy cảm như loại thao tác, mã lỗi và thời gian xử lý, nhưng cũng tránh tiết lộ quá nhiều về đầu vào.

### 8.2. String.valueOf và new String

~~~java
// Không nên chuyển dữ liệu nhạy cảm thành String chỉ để tiện thao tác.
String copy = String.valueOf(password);
~~~

Xóa char[] sau đó không xóa nội dung String đã tạo. Không dùng **new String(password)**, **String.valueOf(password)**, **StringBuilder.append(password)** hoặc interpolation/formatting không kiểm soát để vô tình tạo dữ liệu chứa secret trong một object khó xóa.

### 8.3. Dùng char[] làm key trong collection

Nếu dùng mảng làm key trong HashMap, bạn vừa không có so sánh nội dung như String, vừa dễ kéo dài vòng đời mảng trong bộ nhớ. Không lưu credential dạng char[] trong global cache, static field, session map hoặc thread-local kéo dài ngoài nhu cầu.

Nếu một thành phần buộc phải giữ credential dài hơn, điều đó đòi hỏi chính sách thiết kế riêng (scope, rotation, invalidation, trách nhiệm cleanup, quyền truy cập), không thể chỉ dựa vào lời gọi Arrays.fill cuối chương trình.

### 8.4. So sánh trực tiếp mật khẩu không phải cách xác thực

~~~java
// Không phải giải pháp xác thực mật khẩu production.
boolean equal = Arrays.equals(candidate, expected);
~~~

Đây chỉ là mảnh minh họa một API so sánh array, **không** phải kiểm tra mật khẩu an toàn. **Arrays.equals(...)** không được hứa hẹn là so sánh constant-time; không dùng nó để tuyên bố chống timing side channel.

Hệ thống thực tế thường không lưu plaintext password để so sánh. Việc xác minh credential cần theo protocol/chính sách bảo mật của ứng dụng, với thuật toán hashing/KDF thích hợp và thư viện đáng tin. Bài này chỉ giải thích **vòng đời dữ liệu trong bộ nhớ**, không triển khai một hệ thống xác thực.

### 8.5. Dữ liệu chuyển từ char[] sang byte[]

Một số API nhận **byte[]** (ví dụ trong mã hóa, giao tiếp mạng hoặc thư viện có encoding riêng). Việc chuyển đổi từ UTF-16 char sang UTF-8 bytes là một bước tạo **biểu diễn và buffer khác**, cần:

- Xác định charset rõ ràng, tránh conversion tùy tiện phụ thuộc platform.
- Không đưa bí mật qua một String trung gian chỉ để lấy bytes nếu có API xử lý trực tiếp char/CharBuffer.
- Dọn **cả char[] và byte[] mà bạn sở hữu**, cũng như các buffer tạm có thể truy cập.
- Hiểu rằng một số encoder/native APIs tạo bản sao nội bộ mà caller không thể trực tiếp ghi đè.
- Không dùng cách chuyển đổi tự viết khiến Unicode/surrogate pairs bị sai; char[] biểu diễn **UTF-16 code units**, không nhất thiết mỗi char là một ký tự người dùng cảm nhận.

Với cryptography API nhận char[], hãy kiểm tra contract: nó có thể **copy nội bộ** thay vì giữ reference. Việc bạn xóa mảng ban đầu không tự xóa bản sao của thư viện.

## 9. Một ví dụ về bản sao do API bảo mật tạo ra

Lớp **javax.crypto.spec.PBEKeySpec** (JDK) dùng char[] trong một số workflow tạo key từ password. Constructor nhận char[] và **tạo bản sao nội bộ**; **clearPassword()** có thể xóa bản sao được giữ trong PBEKeySpec, còn **getPassword()** trả về bản sao mà caller phải quản lý.

Về lifecycle, nếu ứng dụng dùng API này, phải xem xét ít nhất:

~~~text
Console trả original char[]
       │
       ├── ứng dụng có original: Arrays.fill(original, '\0')
       │
       └── PBEKeySpec giữ bản sao nội bộ
               │
               ├── clearPassword() khi xong
               └── nếu getPassword() tạo bản sao cho caller:
                       caller phải xóa bản sao đó
~~~

**Đây chỉ là minh họa contract quản lý bộ nhớ, không phải hướng dẫn xây quy trình hashing mật khẩu.** Thuật toán, salt, số vòng lặp/cost và việc sử dụng KDF phải tuân thủ tiêu chuẩn bảo mật hiện hành của hệ thống. Đừng sao chép một tham số KDF cũ chỉ vì xuất hiện trong ví dụ trên mạng.

## 10. Những giới hạn thật của xóa bộ nhớ trong JVM

**Arrays.fill(password, '\0')** ghi vào các phần tử của **đúng mảng** mà code đang tham chiếu. Nó không cung cấp bảo đảm mật mã học rằng mọi bản sao đã biến mất khỏi hệ thống.

Các giới hạn thực tế:

1. **JVM/GC có thể di chuyển hoặc sao chép object trong bộ nhớ.** Người viết ứng dụng không thể theo dõi và xóa mọi bản sao ở tầng runtime.
2. **Thư viện có thể tạo buffer nội bộ** khi giải mã ký tự, thực hiện KDF, chuẩn bị native calls hoặc truyền dữ liệu qua mạng.
3. **Hệ điều hành có thể tạo snapshot, swap hoặc dump** tùy cấu hình; Arrays.fill không kiểm soát các cơ chế này.
4. **Kẻ tấn công có đủ quyền truy cập tiến trình** có thể quan sát dữ liệu trong lúc nó còn cần thiết để xử lý. Giảm thời gian lưu giúp giảm cơ hội, không loại bỏ hoàn toàn.
5. **Chương trình có thể bị kill/crash** trước khi finally thực thi. Không có lời hứa cleanup khi mọi hình thức kết thúc bất thường.
6. **Dữ liệu có thể đã rò rỉ qua log/telemetry trước khi cleanup.** Dọn mảng sau đó không thu hồi được log đã gửi.
7. **Java bytecode/JIT và tối ưu hóa runtime** không cung cấp trong API Arrays.fill một contract "secure erase toàn bộ bản sao vật lý". Không suy diễn rằng đã xóa array nghĩa là đã xóa toàn hệ thống.

Vì vậy nên nói chính xác: **char[] + Arrays.fill giảm thời gian dữ liệu còn tồn tại trong một buffer có thể thay đổi**. Nó là một phần của thiết kế bảo mật nhiều lớp, không thay thế bảo vệ hệ điều hành, vận hành, giao thức hay chính sách lưu trữ.

### 10.1. Khi nào ưu tiên một secret manager thay cho nhập Console?

Nếu ứng dụng chạy không người điều khiển (service, background job, CI pipeline), việc hỏi mật khẩu từ Console có thể không phù hợp. Nên cân nhắc cơ chế nhận dữ liệu từ hệ thống quản lý bí mật được tổ chức theo chính sách của sản phẩm, với phạm vi quyền hạn, audit, rotation và không log secret.

**Không tự động chuyển sang environment variable hoặc command-line argument và coi chúng là tương đương bảo mật**: tùy nền tảng, chúng có thể bị lộ qua process listing, shell history, môi trường con, logs hoặc công cụ chẩn đoán. Cần đánh giá đường truyền và quyền truy cập của từng cơ chế.

### 10.2. Các tình huống không nên dùng Console

- Ứng dụng web hoặc mobile: người dùng nhập qua UI và đường truyền riêng; không có Console JVM trực tiếp.
- Service trong container không có TTY: không giả định sẽ có người nhập vào stdin.
- Unit test tự động: không đưa credential thật vào test; dùng mảng giả hoặc test doubles.
- Hệ thống cần credential rotation dài hạn: quản lý qua API/secret store chuyên dụng, không giữ plaintext trong field không giới hạn.

## 11. Những lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| **System.console() == null** | Không có console theo môi trường/JDK | Dừng an toàn hoặc dùng luồng input chuyên dụng được thiết kế phù hợp |
| Prompt xuất hiện nhưng không nhận dữ liệu | EOF dù Console khác null | Kiểm tra **readPassword() == null** |
| Mật khẩu xuất hiện trên màn hình | Dùng **readLine** hoặc in lại char[] | Dùng readPassword; không xuất secret qua stdout/stderr |
| Dùng **Arrays.fill** nhưng vẫn thấy secret trong heap dump | Có bản sao String/char[]/byte[] hoặc bản sao nội bộ | Tìm copy và trách nhiệm cleanup; giảm thời gian sống, không tuyên bố zeroize tuyệt đối |
| Dữ liệu vẫn còn khi callback lỗi | Dọn sau lệnh xử lý thay vì trong finally | Đưa Arrays.fill vào finally của bên sở hữu |
| Validation chạy bất đồng bộ đọc toàn ký tự '\0' | Array bị xóa trước khi task thực sự sử dụng | Thiết kế lifecycle/ownership async, không dọn trước khi hoàn tất |
| **NullPointerException** lúc fill | readPassword trả null vì EOF | Kiểm tra null trước khi xử lý/xóa |
| Đầu vào không rỗng nhưng đăng nhập không được | Ví dụ chỉ kiểm tra độ dài, không xác thực | Dùng cơ chế xác thực thực sự; không áp dụng đoạn demo làm login |
| Kết quả test không có Console trong IDE | IDE/terminal tích hợp và JDK có kết nối console khác | Kiểm thử trực tiếp trong TTY phù hợp, xử lý null/EOF |
| Ký tự Unicode xử lý sai | Cắt char[] theo giả định một char = một code point hoặc chuyển charset sai | Hiểu UTF-16, dùng API Unicode/encoding chuẩn |
| Lộ dữ liệu khi ghi log | In char[] hoặc dữ liệu từ converter/String | Xóa các đường log; kiểm tra loggers, tracers, exception/reporting |
| Mảng đã xóa nhưng thư viện vẫn giữ secret | API copy dữ liệu đầu vào nội bộ | Kiểm tra lifecycle/clear API riêng của thư viện |
| Mã kiểm thử ghi luôn bí mật test ra output | Debug code dùng println(Arrays.toString(...)) | Chỉ in boolean xác minh cleanup, không in nội dung |
| Chạy nhiều lần bị hành vi khác nhau | Console state, EOF, host terminal khác nhau | Tách test logic trong RAM với test tương tác tích hợp |

### 11.1. Checklist khi sửa lỗi

1. **Xác định điểm nhận dữ liệu:** Console.readPassword, GUI input hay secret manager.
2. **Liệt kê từng lần copy:** String, char[], byte[], char buffer, thư viện, serialization, logs.
3. **Đánh dấu chủ sở hữu:** ai có thể dọn từng buffer và khi nào cleanup hợp lệ.
4. **Theo dõi các đường thoát:** success, return sớm, validation fail, exception, EOF và thread cancellation.
5. **Đưa cleanup vào finally** cho mọi buffer có thể thay đổi mà ứng dụng sở hữu.
6. **Xác nhận không log:** stdout, stderr, hệ thống telemetry và exception message.
7. **Kiểm thử bằng dữ liệu giả:** xác minh array sau cleanup và đảm bảo exception vẫn kích hoạt cleanup.
8. **Kiểm tra vận hành:** quyền process, heap dumps, retention, ranh giới giữa các dịch vụ.
9. **Phân biệt phạm vi bảo đảm:** xóa một array thành công không có nghĩa mọi bản sao ở mọi tầng đã biến mất.

## 12. Unit test và integration test nên kiểm tra gì?

Ví dụ ở phần 6 tách **self-test không tương tác** khỏi **readPassword tương tác**, cho phép CI kiểm tra behavior cleanup ngay cả khi không có terminal.

Một ma trận thử nghiệm hợp lý:

| Test | Đầu vào | Điều phải xác minh |
| --- | --- | --- |
| Normal flow | char[] giả có vài ký tự | Callback chạy; sau return mọi phần tử array gốc là '\0' |
| Exception flow | char[] giả, callback throw | Exception không làm mất cleanup |
| Empty array | char[] dài 0 | Logic xử lý riêng dữ liệu rỗng; cleanup không lỗi |
| Không có Console | Môi trường không tạo Console | Không fallback sang readLine; dừng an toàn |
| EOF | Console trả null | Không xử lý null như credential hợp lệ |
| Copy path | Tạo clone của mảng giả | Xóa mảng gốc không tự xóa clone; cleanup cả hai |
| Logging | Cùng test flow | Không xuất dữ liệu hoặc ký tự giả ra log |
| Unicode | Một số ký tự ngoài BMP trong input giả | Không cắt/sửa theo giả định char[] length là số code points |
| API bên ngoài | Thư viện nhận char[] | Xác nhận contract về copy/retention/clear |
| Integration | Terminal thật có người nhập | Xác nhận echo bị tắt trong môi trường hỗ trợ, cancel/EOF xử lý đúng |

Không nên tạo unit test bắt buộc có người gõ secret; test xử lý array trước, rồi dùng bài kiểm thử tích hợp có điều kiện cho phần Console. Không cần nhập mật khẩu thật để xác nhận việc dọn bộ nhớ.

### 12.1. Tự tạo test cho exception path

Đoạn **selfTest()** đã tạo mảng **failing** và gọi callback ném **IllegalStateException**. Vì **Arrays.fill** nằm trong finally, sau khi catch exception, hàm **isCleared(failing)** trả true.

Đây là một trong những test quan trọng nhất: nếu chỉ kiểm thử đường thành công, có thể không phát hiện cleanup bị bỏ qua khi code ngoại lệ hoặc return sớm.

## 13. Nguyên tắc thiết kế cho ứng dụng thật

### 13.1. Không biến char[] thành một kiểu dữ liệu lưu trữ dài hạn

**char[]** nên mang ý nghĩa buffer bí mật **ngắn hạn**, không phải một credential object lưu trong memory cache vô thời hạn. Nếu yêu cầu nghiệp vụ bắt buộc lưu, phải có chính sách bảo mật riêng về thời gian sống, dữ liệu có thể được thay thế, quyền truy cập và cách dọn.

### 13.2. Một chủ sở hữu cho mỗi mảng

Nếu caller sở hữu và caller dọn, API callee phải **không lưu/copy mảng ngoài phạm vi đã công bố**. Nếu callee nhận quyền sở hữu, caller không được tiếp tục sử dụng mảng. Hai kiểu contract có thể dùng, nhưng phải rõ ràng và nhất quán để không xảy ra use-after-clear hoặc leak.

Dù Java có garbage collector, đó không phải cơ chế thay thế cho việc dọn bí mật ngắn hạn mà code có thể làm một cách chủ động.

### 13.3. Dọn từng bản sao có thể tiếp cận

Nếu phải tạo char[] clone, byte[] hay crypto key/spec chứa bản sao, lập kế hoạch dọn từng nơi theo API của nó. Không dọn object đang được library sử dụng trước khi library hoàn tất công việc; ngược lại, không giữ bản sao sau khi không còn cần.

### 13.4. Không coi một library không giữ tham chiếu là không sao chép

Một API có thể nhận char[] nhưng tạo bản sao bên trong và không giữ reference gốc. Điều đó có thể tốt cho tính đúng đắn của API, song cũng tạo vùng nhớ mới chứa secret. Đọc tài liệu API để biết có **destroy/clear/close** riêng và liệu gọi method **getPassword()** có tạo thêm copy.

### 13.5. Không đưa bí mật ra các kênh quan sát

Cấu hình application logger, tracing, error reporting, metrics, test reports và diagnostic collection để **không thu thập giá trị secret**. Nếu hệ thống cần audit sự kiện xác thực, ghi kết quả nghiệp vụ và định danh đã được xử lý theo chính sách, không ghi passphrase.

### 13.6. Thiết kế tương tác rõ khi không có terminal

Một CLI chỉ dành cho người dùng nhập tay nên báo rằng không có terminal/đầu vào, thay vì âm thầm đọc từ stdin bằng cơ chế echo hoặc chuyển sang một argument chứa secret. Với automation, thiết kế secret injection riêng; không làm suy yếu hợp đồng bảo mật của chương trình dòng lệnh.

### 13.7. Đừng tự xây xác thực chỉ vì đã có char[]

Kỹ thuật quản lý buffer không đồng nghĩa thuật toán xác thực. Hệ thống cần các lựa chọn phù hợp về credential verification, KDF, rate limiting, secure transport và phân quyền; những phần đó phải được đánh giá theo yêu cầu bảo mật hiện hành, không copy tham số hoặc cách so sánh từ ví dụ học tập.

## 14. Bài tập tự luyện

1. Sửa ví dụ để **không chấp nhận input rỗng** và trả về một trạng thái riêng, vẫn bảo đảm finally dọn char[] trong mọi nhánh.
2. Bổ sung test với callback return sớm trong nhiều nhánh và khẳng định array đã được Arrays.fill.
3. Tạo clone của mảng test, sau đó chỉ xóa mảng gốc. Quan sát clone còn ký tự; viết thêm cleanup cho clone và khẳng định cả hai đã bị ghi đè.
4. Thử dùng **new String(char[])** trong một hàm demo và giải thích vì sao xóa char[] không đồng nghĩa xóa String, không in bất kỳ nội dung nào.
5. Viết một abstraction có contract rõ ai sở hữu buffer: caller hoặc callee. Thêm unit test kiểm tra điều gì xảy ra nếu caller tiếp tục dùng array sau khi callee đã dọn.
6. Chạy chương trình từ terminal tương tác, từ IDE và từ môi trường có stdin kết thúc. So sánh nhánh **System.console()==null** và **readPassword()==null**, không tạo fallback không an toàn.
7. Giả sử một SDK nhận chỉ String. Viết phần phân tích threat model: bản sao nào không chủ động xóa được, có SDK/API thay thế không và cần kiểm soát logs/lifecycle thế nào.
8. Thêm test kiểm tra không có ký tự nào từ buffer test xuất hiện trong stdout/stderr khi chạy các nhánh callback.

## 15. Checklist trước khi đưa Console.readPassword vào sản phẩm

- [ ] Chỉ dùng **readPassword** để nhận secret qua console tương tác; không dùng readLine/Scanner cho mục đích đó.
- [ ] Xử lý cả **System.console() == null** lẫn **readPassword() == null** vì EOF.
- [ ] Chọn đúng ranh giới quyền sở hữu **char[]** và đặt cleanup trong **finally**.
- [ ] Không tạo String mới từ char[] nếu không thật sự bắt buộc.
- [ ] Không log/in/serialize secret hoặc đưa vào argument/env tùy tiện.
- [ ] Nếu phải copy, mỗi bản sao có cleanup và giới hạn vòng đời riêng.
- [ ] Không xóa array trước khi mọi consumer hợp lệ dùng xong.
- [ ] Không giữ buffer trong field, cache, static storage hoặc async task không kiểm soát.
- [ ] Kiểm thử nhánh exception và return sớm bằng dữ liệu giả.
- [ ] Xác nhận UI/terminal thực tế có hỗ trợ nhập không echo.
- [ ] Phân biệt xóa array đã kiểm tra với cam kết xóa mọi bản sao trong JVM/OS.
- [ ] Đánh giá cả quyền process, logs, heap dump, secret store, giao thức và chính sách xác thực.

## Kết luận

Với một chương trình Java CLI cần nhận dữ liệu nhạy cảm, mẫu an toàn hơn là:

**Console.readPassword → nhận char[] ngắn hạn → xác nhận null/EOF → xử lý qua API phù hợp → Arrays.fill trong finally → không giữ bản sao hoặc reference ngoài vòng đời đã định.**

Cách làm này giảm thời gian bí mật còn hiện diện trong một array mà chương trình có quyền điều khiển, nhưng không bảo đảm mọi bản sao ở tầng JVM/hệ điều hành được xóa hoàn toàn. Giá trị thực của **char[]** nằm ở một **lifecycle và ownership rõ ràng**, kết hợp giảm thiểu log, giới hạn quyền và biện pháp bảo mật hệ thống phù hợp.

**Tài liệu tham khảo chính thức, còn áp dụng:**

- [Console — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Console.html)
- [Arrays.fill(char[],char) — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html)
- [String — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html)
- [PBEKeySpec — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html)
- [Console — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html)