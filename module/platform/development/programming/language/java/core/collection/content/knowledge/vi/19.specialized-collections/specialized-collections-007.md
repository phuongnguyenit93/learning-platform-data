# Hashtable, Dictionary và Properties trong mã đời cũ

## 1. Đọc đúng vai trò trước khi thay lớp

Khi bảo trì một ứng dụng Java lâu năm, có thể gặp Dictionary trong chữ ký phương thức, Hashtable trong vùng dữ liệu dùng chung và Properties ở chỗ nạp cấu hình.

Ba tên này có quan hệ kế thừa, nhưng không có cùng mục đích:

| Thành phần | Vai trò cần nhận diện |
| --- | --- |
| Dictionary<K,V> | Lớp trừu tượng cũ biểu diễn ánh xạ khóa–giá trị |
| Hashtable<K,V> | Một triển khai bảng băm có đồng bộ, đồng thời hỗ trợ giao diện Map |
| Properties | Bộ thuộc tính dạng chuỗi với đọc/ghi cấu hình và cơ chế giá trị mặc định |

Nếu coi cả ba chỉ là “Map cũ”, có thể thay mã biên dịch được nhưng làm đổi null, đồng bộ, cách duyệt hoặc cách tìm giá trị mặc định.

Mục tiêu khi đọc mã đời cũ là xác định hợp đồng mà đoạn mã đang dựa vào. Sau đó mới quyết định giữ một ranh giới tương thích, chuyển sang Map hay tiếp tục dùng Properties cho đúng công việc cấu hình của nó.

Từ “đời cũ” ở đây không đồng nghĩa cả ba lớp đều có annotation @Deprecated. Trong API Java 17, Dictionary được mô tả là obsolete; Hashtable và Properties vẫn là các API có mặt để sử dụng và tương thích. Phương thức Properties.save mới là một ví dụ có đánh dấu deprecated cụ thể.

Bài dùng Java 17+ và bốn chương trình độc lập. Mỗi ví dụ có tên tệp, lệnh chạy và stdout; không dựa vào thứ tự duyệt ngẫu nhiên của bảng băm.

## 2. Quan hệ giữa Dictionary, Hashtable, Map và Properties

Có thể đọc quan hệ kiểu như sau:

```text
Object
└── Dictionary<K,V>
    └── Hashtable<K,V>  implements Map<K,V>
        └── Properties  extends Hashtable<Object,Object>
```

### 2.1. Dictionary là lớp trừu tượng, không phải tên khác của Map

Dictionary có các phép cơ bản như get, put, remove, size, isEmpty và hai phương thức keys/elements trả Enumeration.

Nó không khai báo triển khai Map. Vì vậy một biến có kiểu Dictionary không tự có keySet hay entrySet chỉ vì đối tượng thực tế bên dưới có thể là Hashtable.

Ngược lại, một Map bất kỳ không tự là Dictionary. Không thể đổi tất cả chữ Dictionary thành Map ở một phía rồi giả định mọi bên gọi cũ vẫn nhận đúng kiểu.

Tài liệu [Dictionary Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Dictionary.html) hướng các triển khai mới tới Map thay vì mở rộng Dictionary.

### 2.2. Hashtable là cầu nối qua quan hệ kiểu

Một đối tượng Hashtable có thể được nhìn qua biến Dictionary hoặc biến Map mà không cần sao chép dữ liệu.

Ba biến trỏ tới cùng đối tượng vẫn cùng nhìn một bảng. Đổi kiểu biến tham chiếu không biến Hashtable thành HashMap, không bỏ đồng bộ và không mở quyền nhận null.

Ngược lại, tạo một HashMap mới rồi chép các ánh xạ là một hành động tạo bảng khác. Bản sao không tự cập nhật theo bảng nguồn.

### 2.3. Properties kế thừa một bề mặt rộng hơn ý nghĩa cấu hình

Properties kế thừa Hashtable<Object,Object>, không phải Hashtable<String,String>.

API cấu hình của nó muốn tên thuộc tính và giá trị đều là String. Tuy nhiên API kế thừa như put(Object,Object) vẫn tồn tại, nên trình biên dịch không chặn mọi trường hợp đưa sai kiểu vào.

Đây là một điểm cần đọc bằng ý nghĩa API, không chỉ nhìn phương thức nào gọi được.

## 3. Dictionary và Enumeration: đọc một API cũ có kiểm soát

### 3.1. Cách duyệt cơ bản

Enumeration có hai phương thức quen thuộc:

| Enumeration | Ý nghĩa |
| --- | --- |
| hasMoreElements() | Còn phần tử để lấy hay không |
| nextElement() | Lấy phần tử kế tiếp; hết phần tử thì có thể ném NoSuchElementException |

Để đọc từng cặp từ Dictionary, có thể duyệt keys rồi gọi get(key). Không cần ép kiểu thô hoặc giả định hai luồng duyệt keys và elements có thể ghép từng vị trí với nhau.

Một Enumeration không trực tiếp cung cấp thao tác remove như Iterator. Java 9+ có asIterator để thích nghi với mã nhận Iterator; thao tác remove của bộ thích nghi mặc định không được hỗ trợ. Không tiếp tục dùng cả Enumeration gốc lẫn Iterator ấy xen kẽ để điều khiển cùng lần duyệt. Xem [Enumeration Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Enumeration.html).

### 3.2. Ví dụ 1: cùng đối tượng khác với bản sao

Lưu thành **LegacyDictionaryBridge.java**:

```java
import java.util.Dictionary;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.Hashtable;
import java.util.Map;
import java.util.TreeMap;

public class LegacyDictionaryBridge {
    static <K, V> Map<K, V> copyEntries(Dictionary<K, V> source) {
        Map<K, V> copy = new HashMap<>();
        Enumeration<K> keys = source.keys();
        while (keys.hasMoreElements()) {
            K key = keys.nextElement();
            copy.put(key, source.get(key));
        }
        return copy;
    }

    public static void main(String[] args) {
        Hashtable<String, Integer> table = new Hashtable<>();
        Dictionary<String, Integer> dictionary = table;
        Map<String, Integer> alias = table;
        dictionary.put("alpha", 10);
        dictionary.put("beta", 20);

        Map<String, Integer> copy;
        synchronized (table) {
            copy = copyEntries(dictionary);
        }
        System.out.println("dictionary alpha: " + dictionary.get("alpha"));
        System.out.println("contains beta as value: " + table.contains("beta"));
        System.out.println("containsKey beta: " + table.containsKey("beta"));
        System.out.println("contains value 20: " + table.contains(20));
        System.out.println("copy before update: " + new TreeMap<>(copy));

        table.put("alpha", 99);
        System.out.println("alias alpha after update: " + alias.get("alpha"));
        System.out.println("copy alpha after update: " + copy.get("alpha"));

        try {
            table.put(null, 1);
        } catch (NullPointerException expected) {
            System.out.println("null key: rejected");
        }
        try {
            table.put("gamma", null);
        } catch (NullPointerException expected) {
            System.out.println("null value: rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LegacyDictionaryBridge.java
java LegacyDictionaryBridge
```

Stdout:

```text
dictionary alpha: 10
contains beta as value: false
containsKey beta: true
contains value 20: true
copy before update: {alpha=10, beta=20}
alias alpha after update: 99
copy alpha after update: 10
null key: rejected
null value: rejected
```

Các chương trình trong bài được biên dịch với --release 17 và chạy trên OpenJDK 24.0.2. Cờ --release chọn mức ngôn ngữ/API và bytecode đích, không đổi phiên bản JVM thực thi.

### 3.3. Vì sao alias thấy 99 còn copy vẫn là 10?

Các biến dictionary, table và alias cùng trỏ tới đối tượng Hashtable. Bởi vậy thay alpha qua table được nhìn thấy qua alias.

Biến copy là HashMap mới chứa các ánh xạ đã đọc trước đó. Việc thay liên kết alpha trong bảng nguồn không thay liên kết alpha ở bản sao.

Đây là bản sao các ánh xạ, không phải sao chép sâu mọi đối tượng khóa/giá trị. Nếu value là một đối tượng khả biến được chia sẻ, hai bảng vẫn có thể nhìn cùng đối tượng value.

TreeMap trong lệnh in chỉ làm thứ tự stdout ổn định theo khóa String. Không phải bằng chứng Hashtable hay HashMap giữ thứ tự chữ cái.

### 3.4. Đồng bộ khi chép phụ thuộc đối tượng nguồn thực tế

Hàm copyEntries không tự cung cấp một giao dịch sao chép an toàn cho mọi triển khai Dictionary.

Trong ví dụ, nguồn thực tế là Hashtable và đoạn gọi bao toàn bộ lần duyệt bằng synchronized(table). Điều này dùng cùng đối tượng giám sát với các thao tác đồng bộ của Hashtable; không có thao tác sửa nào khác trong chương trình chen vào.

Với một triển khai Dictionary khác, phải đọc hợp đồng đồng thời của nó. Chỉ đặt synchronized lên một biến tham chiếu bất kỳ không tự bảo đảm mọi bên ghi đều phối hợp trên cùng khóa đồng bộ.

## 4. Những đặc điểm Hashtable thường làm thay đổi kết quả bảo trì

### 4.1. Không nhận null ở cả khóa lẫn giá trị

Hashtable từ chối put(null, value) và put(key, null). Các phép tra như get(null) cũng không phải cách hỏi về một khóa null hợp lệ.

Với trạng thái hợp lệ không có value null, get trả null có nghĩa không có ánh xạ cho khóa đang hỏi tại lần truy cập đó.

Không chuyển ý này thành bảo đảm rằng ánh xạ vẫn vắng mặt sau đó khi có luồng khác đang cập nhật.

[Tài liệu Hashtable Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Hashtable.html) nêu chính sách null và quan hệ equals/hashCode của khóa.

### 4.2. `contains` trong mã cũ tìm value

Tên contains(Object) dễ bị đọc nhầm thành “có khóa này không”. Ở Hashtable, nó kiểm tra value, cùng ý nghĩa chức năng với containsValue.

Trong ví dụ:

- `contains`("beta") là false vì không có value String "beta".
- `containsKey`("beta") là true vì có khóa beta.
- `contains`(20) là true vì beta gắn với value 20.

Khi chuyển mã sang Map, hãy dịch đúng ý nghĩa sang containsValue hoặc containsKey. Không thay theo tên gần giống.

### 4.3. Không có cam kết thứ tự duyệt

Hashtable không cung cấp hợp đồng thứ tự chèn hay thứ tự sắp xếp khóa.

Nếu một kiểm thử so cả chuỗi toString có nhiều khóa, kết quả có thể đang phụ thuộc chi tiết triển khai không cần thiết. Khi thứ tự là yêu cầu thật, hãy biểu diễn yêu cầu ấy bằng cấu trúc hoặc bước sắp xếp thích hợp.

Khóa vẫn cần equals/hashCode nhất quán. Việc có synchronized không sửa được một khóa bị đổi các trường dùng tính hash khi đang nằm trong bảng.

### 4.4. Enumeration và Iterator không có cùng hợp đồng

Với Hashtable:

| Cách duyệt | Điều cần nhớ |
| --- | --- |
| keys()/elements() trả Enumeration | Không fail-fast; nếu sửa cấu trúc trong lúc duyệt, kết quả không được xác định theo hợp đồng |
| Iterator từ các collection view | Có cơ chế fail-fast theo best effort đối với sửa cấu trúc ngoài đường được cho phép |
| Duyệt một lần với nhiều lời gọi | Không tự là một thao tác nguyên tử chỉ vì từng phương thức map có đồng bộ |

Không nhận được ConcurrentModificationException không chứng minh Enumeration đang duyệt an toàn. Ngoại lệ fail-fast cũng không phải cơ chế bảo vệ dữ liệu dùng chung.

Đừng suy tiếp bảng này sang mọi lớp con: Properties có mô tả iterator riêng trong Java 17.

### 4.5. Đồng bộ là một đặc điểm, không phải câu trả lời cho mọi thao tác

Hashtable bảo vệ các thao tác của nó bằng cơ chế đồng bộ. Điều đó không tự làm một chuỗi do ứng dụng viết thành một thao tác không thể bị chen giữa.

Cũng không có bảo đảm mọi trường bên trong một value khả biến được giữ trong bảng đều được bảo vệ khi ứng dụng tự sửa chúng ngoài map.

Khi bảo trì, cần xác định dữ liệu được bảo vệ, ranh giới thao tác và tất cả nơi truy cập cùng dữ liệu.

## 5. Ví dụ 2: vì sao hai lời gọi an toàn riêng vẫn có thể mất cập nhật?

### 5.1. Một lịch xen kẽ đủ gây lỗi

Muốn tăng hits, hai luồng đều có thể đọc cùng giá trị 0 rồi mỗi luồng ghi lại 1:

| Thời điểm | Luồng A | Luồng B |
| --- | --- | --- |
| 1 | get nhận 0 | |
| 2 | | get nhận 0 |
| 3 | put 1 | |
| 4 | | put 1 |

Không có get hay put nào cần làm hỏng cấu trúc bảng. Lỗi nằm ở ý định “đọc rồi tăng rồi ghi” chưa được bảo vệ như một đơn vị.

Chương trình dưới dùng CyclicBarrier để buộc cả hai luồng đọc xong trước khi ghi. Vì vậy kết quả 1 ở phần đầu được tạo có chủ đích, không phải mong một lỗi tranh chấp tình cờ xuất hiện.

### 5.2. Chương trình đầy đủ

Lưu thành **HashtableCompoundActions.java**:

```java
import java.util.Hashtable;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class HashtableCompoundActions {
    static int separatedReadWrite(ExecutorService pool) throws Exception {
        Hashtable<String, Integer> counter = new Hashtable<>();
        counter.put("hits", 0);
        CyclicBarrier bothRead = new CyclicBarrier(2);
        Callable<Void> increment = () -> {
            int before = counter.get("hits");
            bothRead.await(5, TimeUnit.SECONDS);
            counter.put("hits", before + 1);
            return null;
        };
        Future<Void> first = pool.submit(increment);
        Future<Void> second = pool.submit(increment);
        first.get(5, TimeUnit.SECONDS);
        second.get(5, TimeUnit.SECONDS);
        return counter.get("hits");
    }

    static int protectedIncrements(ExecutorService pool, boolean useMerge)
            throws Exception {
        Hashtable<String, Integer> counter = new Hashtable<>();
        counter.put("hits", 0);
        Runnable increment = () -> {
            for (int i = 0; i < 1000; i++) {
                if (useMerge) {
                    counter.merge("hits", 1, Integer::sum);
                } else {
                    synchronized (counter) {
                        int before = counter.get("hits");
                        counter.put("hits", before + 1);
                    }
                }
            }
        };
        Future<?> first = pool.submit(increment);
        Future<?> second = pool.submit(increment);
        first.get(5, TimeUnit.SECONDS);
        second.get(5, TimeUnit.SECONDS);
        return counter.get("hits");
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            System.out.println("two separated increments: " + separatedReadWrite(pool));
            System.out.println("locked increments: " + protectedIncrements(pool, false));
            System.out.println("merge increments: " + protectedIncrements(pool, true));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashtableCompoundActions.java
java HashtableCompoundActions
```

Stdout:

```text
two separated increments: 1
locked increments: 2000
merge increments: 2000
```

### 5.3. Hai cách bảo vệ phù hợp với ví dụ

Khối synchronized(counter) giữ cả get và put trong cùng phạm vi đồng bộ. Với cùng đối tượng Hashtable và các bên truy cập phối hợp đúng, một lần tăng được thực hiện trọn trước khi lần tăng khác vào đoạn ấy.

Cách merge dùng thao tác cập nhật phù hợp thay cho hai lời gọi tách rời. Trong triển khai OpenJDK 17, Hashtable override merge bằng phương thức đồng bộ; có thể đối chiếu [Hashtable.java](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Hashtable.java).

Ví dụ dùng hàm cộng ngắn, không sửa lại map từ bên trong hàm truyền vào. Không mở rộng kết luận thành “mọi merge của mọi Map đều nguyên tử”: cần đọc hợp đồng của triển khai cụ thể.

Hai luồng trong mỗi phần bảo vệ thực hiện 1.000 lần tăng, nên kết quả cuối là 2.000. Time-out của barrier/Future giúp thí nghiệm báo lỗi nếu không hoàn tất; chúng không quyết định thứ tự in đầu ra.

### 5.4. Thay Hashtable bằng ConcurrentHashMap vẫn cần chọn đúng thao tác

ConcurrentHashMap cung cấp các thao tác cập nhật đồng thời có hợp đồng riêng. Nó không tự gộp một đoạn get rồi put do ứng dụng viết thành một lần tăng nguyên tử.

Nếu yêu cầu là tăng theo khóa, phải dùng thao tác thích hợp hoặc một mô hình bảo vệ phù hợp. Nếu yêu cầu liên quan nhiều khóa cùng lúc, còn cần xem bất biến của cả nhóm.

Tài liệu [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) là cơ sở để đánh giá việc thay thế, không chỉ so chữ “thread-safe”.

## 6. Properties là dữ liệu cấu hình dạng chuỗi với lớp mặc định

### 6.1. Cặp API nên dùng là setProperty/getProperty

Một thuộc tính cấu hình có tên String và giá trị String. Ví dụ port là chuỗi "8080" khi còn ở lớp đọc cấu hình; ứng dụng sẽ phân tích và kiểm tra thành số nguyên ở ranh giới phù hợp.

`setProperty` nhận hai String. `getProperty` trả String hoặc giá trị dự phòng theo hợp đồng. Cặp này thể hiện ý định rõ hơn API put/get kế thừa.

Do kế thừa Hashtable<Object,Object>, Properties vẫn cho phép một lệnh put("port", 9090) biên dịch. Điều đó đưa Integer vào vùng dữ liệu vốn được kỳ vọng là chuỗi.

Không coi việc gọi được phương thức là bằng chứng kiểu dữ liệu phù hợp với toàn bộ API Properties. Tài liệu [Properties Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) khuyến cáo dùng setProperty và mô tả lỗi khi lưu một bộ thuộc tính có phần tử sai kiểu.

### 6.2. Defaults là nguồn dự phòng, không phải putAll

Một Properties có thể nhận Properties khác làm defaults. `getProperty` tìm trong lớp hiện tại rồi tiếp tục qua chuỗi defaults khi cần.

Các phần tử mặc định không tự được chép vào bảng hiện tại. Do đó get, containsKey và size của phần ánh xạ hiện tại không có cùng ý nghĩa với một phép tra cấu hình hiệu lực qua getProperty.

| Cách đọc | Phạm vi cần hiểu |
| --- | --- |
| get(key) | Ánh xạ trực tiếp trong đối tượng hiện tại, trả Object |
| containsKey(key), size() | Ánh xạ trực tiếp trong đối tượng hiện tại |
| getProperty(name) | Tra thuộc tính String có xét chuỗi defaults |
| getProperty(name, fallback) | Xét chuỗi defaults trước; nếu không có thì trả fallback truyền vào |
| stringPropertyNames() | Tập tên thuộc tính chuỗi, gồm các tên phù hợp từ defaults |
| propertyNames() | Enumeration tên có xét defaults; có thể lỗi nếu bị đưa khóa không phải String |

Xóa một phần ghi đè ở lớp hiện tại có thể làm giá trị mặc định xuất hiện trở lại. `remove` không có nghĩa tên thuộc tính biến mất khỏi toàn bộ chuỗi dự phòng.

### 6.3. Defaults có thể còn được chia sẻ

Nếu ứng dụng tiếp tục giữ đối tượng defaults và sửa nó, kết quả tra ở đối tượng con có thể đổi theo.

Đó là quan hệ tới một nguồn mặc định, không phải lời hứa đã tạo ảnh chụp độc lập lúc gọi constructor.

Khi cần một cấu hình ổn định cho một phiên bản chạy, có thể đọc các giá trị hiệu lực, kiểm tra chúng rồi tạo một cấu trúc dữ liệu ổn định riêng. Không để việc chia sẻ đối tượng vô tình quyết định lúc cấu hình thay đổi.

## 7. Ví dụ 3: get, getProperty, defaults và sai kiểu

Lưu thành **PropertiesDefaultsAndTypes.java**:

```java
import java.io.StringReader;
import java.io.StringWriter;
import java.util.Map;
import java.util.Properties;
import java.util.TreeMap;
import java.util.TreeSet;

public class PropertiesDefaultsAndTypes {
    public static void main(String[] args) throws Exception {
        Properties defaults = new Properties();
        defaults.setProperty("host", "localhost");
        defaults.setProperty("mode", "safe");
        defaults.setProperty("port", "8080");

        Properties config = new Properties(defaults);
        config.setProperty("mode", "fast");
        System.out.println("get host: " + config.get("host"));
        System.out.println("getProperty host: " + config.getProperty("host"));
        System.out.println("containsKey host: " + config.containsKey("host"));
        System.out.println("local size: " + config.size());
        System.out.println("effective names: " + new TreeSet<>(config.stringPropertyNames()));

        config.remove("mode");
        System.out.println("mode after remove override: " + config.getProperty("mode"));
        config.setProperty("mode", "fast");
        defaults.setProperty("host", "server");
        System.out.println("host after defaults change: " + config.getProperty("host"));

        Map<String, String> effective = new TreeMap<>();
        for (String name : config.stringPropertyNames()) {
            effective.put(name, config.getProperty(name));
        }
        System.out.println("effective copy: " + effective);

        StringWriter writer = new StringWriter();
        config.store(writer, null);
        Properties reloaded = new Properties();
        try (StringReader reader = new StringReader(writer.toString())) {
            reloaded.load(reader);
        }
        System.out.println("reloaded mode: " + reloaded.getProperty("mode"));
        System.out.println("reloaded host: " + reloaded.getProperty("host"));
        System.out.println("reloaded names: " + new TreeSet<>(reloaded.stringPropertyNames()));

        config.put("port", 9090);
        System.out.println("raw port type: " + config.get("port").getClass().getSimpleName());
        System.out.println("getProperty port: " + config.getProperty("port"));
        try {
            config.store(new StringWriter(), null);
        } catch (ClassCastException expected) {
            System.out.println("store non-string value: rejected");
        }
        config.put(7, "bad-key");
        try {
            config.propertyNames();
        } catch (ClassCastException expected) {
            System.out.println("propertyNames non-string key: rejected");
        }
        System.out.println("string names after pollution: "
                + new TreeSet<>(config.stringPropertyNames()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 PropertiesDefaultsAndTypes.java
java PropertiesDefaultsAndTypes
```

Stdout:

```text
get host: null
getProperty host: localhost
containsKey host: false
local size: 1
effective names: [host, mode, port]
mode after remove override: safe
host after defaults change: server
effective copy: {host=server, mode=fast, port=8080}
reloaded mode: fast
reloaded host: null
reloaded names: [mode]
raw port type: Integer
getProperty port: 8080
store non-string value: rejected
propertyNames non-string key: rejected
string names after pollution: [host, mode, port]
```

### 7.1. Host tồn tại về mặt cấu hình nhưng không nằm ở bảng hiện tại

Config chỉ có phần ghi đè mode, nên local size bằng 1. `get`("host") trả null và containsKey("host") trả false.

`getProperty`("host") vẫn tìm được "localhost" từ defaults. Tập stringPropertyNames gồm host, mode và port.

Sau khi xóa phần ghi đè mode, getProperty lại thấy "safe". Sau khi sửa host ở defaults, config thấy "server".

Những kết quả này cho thấy không thể thay getProperty bằng get rồi ép kiểu một cách máy móc.

### 7.2. Chép giá trị hiệu lực khác với chép phần tử trực tiếp

Vòng lặp stringPropertyNames/getProperty tạo một bản đồ String–String chứa các giá trị hiệu lực trong điều kiện ví dụ không có ai đồng thời thay cấu hình.

Đây là lựa chọn rõ ràng để đưa dữ liệu cấu hình đã đọc sang một tầng dùng Map. new HashMap<>(config) sẽ chép phần ánh xạ trực tiếp kiểu Object–Object; nó không tự thực hiện cùng phép tra defaults.

Nếu có thay đổi đồng thời hoặc cần một phiên bản cấu hình nhất quán, vòng lặp nhiều lời gọi phải được đặt trong một quy trình công bố/đọc cấu hình phù hợp. Không coi nó là ảnh chụp nguyên tử trong mọi trường hợp.

### 7.3. `store` không tự lưu toàn bộ defaults

Config chỉ ghi trực tiếp mode vào dữ liệu lưu. Khi nạp lại vào Properties mới không có defaults, mode vẫn là fast nhưng host không có.

Nếu muốn một tệp chứa toàn bộ giá trị hiệu lực, cần quyết định rõ việc làm phẳng chuỗi defaults, tạo bộ thuộc tính chuỗi sạch rồi lưu bộ ấy.

Nếu muốn tệp chỉ lưu phần ghi đè để còn dùng nguồn mặc định lúc chạy, hành vi hiện tại lại là điều cần giữ. Không tự thay chính sách trong quá trình bảo trì.

### 7.4. Phần sai kiểu có thể tạo biểu hiện gây hiểu nhầm

Sau put("port", 9090), get trả Integer. Trong ví dụ này, getProperty vẫn trả chuỗi "8080" từ defaults thay vì chuyển Integer 9090 thành String.

Mã nguồn [Properties.java của OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Properties.java) cho thấy getProperty chỉ nhận giá trị kiểu String ở lớp hiện tại trước khi dùng đường dự phòng.

Không dùng đặc điểm đó làm kỹ thuật cấu hình. Nó cho thấy một phần tử sai kiểu có thể bị che bởi giá trị dự phòng, khiến mã đọc thô và mã đọc thuộc tính nhìn dữ liệu khác nhau.

`store` từ chối bộ thuộc tính có value không phải String. `propertyNames` từ chối khi có khóa Integer. `stringPropertyNames` bỏ qua phần tử sai kiểu và vẫn có thể đưa tên port từ defaults vào kết quả.

Tập tên chuỗi không phải phép xác nhận toàn bộ đối tượng không chứa dữ liệu sai kiểu. Cần ngăn hoặc kiểm tra sai kiểu ở ranh giới nhập.

## 8. Định dạng .properties và mã hóa: nhìn rõ hai lớp xử lý

### 8.1. Byte thành ký tự rồi ký tự thành thuộc tính

Khi đọc một tệp, có hai việc khác nhau:

1. Giải mã byte thành ký tự theo một bảng mã.
2. Phân tích cú pháp dòng thuộc tính, dấu phân cách và escape.

`load`(InputStream) có quy tắc ISO-8859-1 riêng. Nó không tự trở thành UTF-8 chỉ vì môi trường Java hiện tại có bộ ký tự mặc định là UTF-8.

`load`(Reader) nhận ký tự đã được Reader giải mã. Muốn đọc tệp UTF-8, tạo Reader với UTF-8 rõ ràng, chẳng hạn qua Files.newBufferedReader hoặc InputStreamReader.

[Files Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) mô tả các API Reader/Writer theo Charset; [Properties Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) quy định overload byte và overload ký tự.

### 8.2. Một mẫu dữ liệu thật, không phải chuỗi literal Java

Phần dưới là nội dung thuộc tính sau khi tạo chuỗi trong chương trình, tương đương dữ liệu một tệp UTF-8:

```properties
# Example properties
message=Chào bạn
path=C:\\temp\\data
joined=first\
  second
escaped\ key:some\:value
empty=
bare
quoted="hello"
duplicate=old
duplicate=new
```

Ở định dạng này:

- Dòng chú thích có dấu # hoặc ! ở vị trí bắt đầu thích hợp.
- Tên và giá trị có thể được tách bằng dấu =, dấu : hoặc khoảng trắng chưa escape theo quy tắc cú pháp.
- Khoảng trắng hoặc dấu phân cách thuộc về tên cần được escape khi có thể gây nhầm.
- Một dòng có tên nhưng không còn phần giá trị tạo giá trị chuỗi rỗng.
- Dấu nháy không tự tạo cú pháp trích dẫn giống JSON; ký tự nháy ở giá trị có thể được giữ nguyên.
- Dấu gạch chéo ngược liên quan tới escape và nối dòng, không phải ký tự luôn được giữ nguyên.

Dòng joined có gạch chéo ngược nối dòng. Dấu ấy, ký tự kết thúc dòng và khoảng trắng đầu dòng kế tiếp bị bỏ; không tự chèn một khoảng trắng vào giữa first và second.

### 8.3. Cẩn thận với đường dẫn và hai lần escape

Muốn dữ liệu giá trị chứa một gạch chéo ngược, tệp .properties thường phải biểu diễn nó bằng hai gạch chéo ngược.

Nếu viết chính nội dung tệp ấy bằng chuỗi literal Java, còn phải xử lý lớp escape của Java. Vì vậy đoạn Java trong chương trình có nhiều gạch chéo hơn nội dung tệp ở trên.

Không sửa số dấu chỉ dựa vào hình thức trông có vẻ dư. Cần xác định đang đọc mã nguồn Java, văn bản properties hay giá trị đã parse.

Một escape không hợp lệ theo kiểu ký tự thông thường có thể bị bộ đọc Properties bỏ dấu gạch chéo; nó không luôn báo lỗi giống trình biên dịch Java. Unicode escape sai dạng lại có thể gây IllegalArgumentException.

Properties cũng không tự mở rộng biến môi trường hay tính biểu thức chỉ vì value chứa một chuỗi có hình thức đặc biệt. Nếu một framework có thêm cơ chế đó, phải phân biệt nó với java.util.Properties.

### 8.4. Chương trình đầy đủ kiểm tra UTF-8, escape và nạp lại

Lưu thành **PropertiesTextAndEncoding.java**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class PropertiesTextAndEncoding {
    public static void main(String[] args) throws Exception {
        String text = "# Example properties\n"
                + "message=Chào bạn\n"
                + "path=C:\\\\temp\\\\data\n"
                + "joined=first\\\n"
                + "  second\n"
                + "escaped\\ key:some\\:value\n"
                + "empty=\n"
                + "bare\n"
                + "quoted=\"hello\"\n"
                + "duplicate=old\n"
                + "duplicate=new\n";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

        Properties fromReader = new Properties();
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(utf8), StandardCharsets.UTF_8)) {
            fromReader.load(reader);
        }
        Properties fromBytes = new Properties();
        try (ByteArrayInputStream input = new ByteArrayInputStream(utf8)) {
            fromBytes.load(input);
        }

        System.out.println("UTF-8 Reader message: "
                + "Chào bạn".equals(fromReader.getProperty("message")));
        System.out.println("byte overload message: "
                + "Chào bạn".equals(fromBytes.getProperty("message")));
        System.out.println("path: " + fromReader.getProperty("path"));
        System.out.println("joined: " + fromReader.getProperty("joined"));
        System.out.println("escaped key: " + fromReader.getProperty("escaped key"));
        System.out.println("empty length: " + fromReader.getProperty("empty").length());
        System.out.println("bare length: " + fromReader.getProperty("bare").length());
        System.out.println("quoted: " + fromReader.getProperty("quoted"));
        System.out.println("duplicate: " + fromReader.getProperty("duplicate"));

        try (StringReader reader = new StringReader("duplicate=latest\n")) {
            fromReader.load(reader);
        }
        System.out.println("second load keeps path: " + fromReader.containsKey("path"));
        System.out.println("second load duplicate: " + fromReader.getProperty("duplicate"));

        StringWriter writer = new StringWriter();
        fromReader.store(writer, null);
        Properties writerRoundTrip = new Properties();
        try (StringReader reader = new StringReader(writer.toString())) {
            writerRoundTrip.load(reader);
        }
        System.out.println("Writer round-trip message: "
                + "Chào bạn".equals(writerRoundTrip.getProperty("message")));

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        fromReader.store(output, null);
        Properties byteRoundTrip = new Properties();
        try (ByteArrayInputStream input = new ByteArrayInputStream(output.toByteArray())) {
            byteRoundTrip.load(input);
        }
        System.out.println("byte round-trip message: "
                + "Chào bạn".equals(byteRoundTrip.getProperty("message")));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 PropertiesTextAndEncoding.java
java PropertiesTextAndEncoding
```

Stdout:

```text
UTF-8 Reader message: true
byte overload message: false
path: C:\temp\data
joined: firstsecond
escaped key: some:value
empty length: 0
bare length: 0
quoted: "hello"
duplicate: new
second load keeps path: true
second load duplicate: latest
Writer round-trip message: true
byte round-trip message: true
```

### 8.5. Vì sao byte overload sai nhưng byte round-trip lại đúng?

Lần đọc đầu đưa các byte UTF-8 vào overload giả định ISO-8859-1. Hai phía không cùng quy tắc giải mã, nên chuỗi tiếng Việt nhận được không bằng dữ liệu mong muốn.

Ở lượt store(OutputStream), Properties viết theo định dạng byte và escape thích hợp của API ấy. `load`(InputStream) đọc lại dữ liệu do chính định dạng tương ứng tạo ra, nên giá trị tiếng Việt được khôi phục.

Điều này không có nghĩa tệp đầu vào ban đầu là UTF-8 nhưng load(InputStream) vẫn nhận đúng mọi trường hợp.

Reader/Writer cũng tạo một cặp nạp–lưu ở tầng ký tự. Khi Writer nối tới một tệp byte thật, người gọi vẫn phải chọn bảng mã cho nó.

### 8.6. `load` thêm dữ liệu, không tự xóa sạch cấu hình cũ

Dữ liệu mẫu có duplicate xuất hiện hai lần; giá trị sau ghi đè giá trị trước.

Sau đó chương trình load một tài liệu khác chỉ có duplicate=latest vào cùng đối tượng. Duplicate đổi thành latest, còn path vẫn có.

Vì vậy “nạp lại” có thể là trộn/ghi đè các khóa được đọc, không phải thay toàn bộ tập cấu hình bằng nội dung tệp mới.

Khi yêu cầu là thay toàn bộ cấu hình, đọc vào đối tượng mới, kiểm tra rồi công bố phiên bản mới thường dễ suy luận hơn việc sửa từng phần trên đối tượng đang được dùng.

## 9. Những quyết định đọc/ghi cần giữ khi bảo trì

### 9.1. `store` bảo toàn dữ liệu thuộc tính, không bảo toàn văn bản gốc

Không dùng load rồi store như một công cụ giữ nguyên chú thích, thứ tự dòng và cách căn lề của tệp gốc.

`store` có thể viết lại escape và có dòng thời gian. Vì vậy chương trình chỉ kiểm tra giá trị sau khi nạp lại, không in cả tệp store để làm stdout cố định.

Nếu một bài kiểm thử cần đối chiếu cấu hình, hãy so dữ liệu và chính sách lưu đúng phạm vi. Nếu yêu cầu là chỉnh sửa một tệp mà giữ nguyên trình bày do con người quản lý, Properties không cung cấp mô hình bảo toàn mọi chi tiết văn bản ấy.

### 9.2. Ai mở tài nguyên thì phải biết ai đóng nó

`load`(Reader) và load(InputStream) không tự đóng đối tượng được truyền vào. `store` thông thường cũng không tự đóng Writer/OutputStream.

Dùng try-with-resources tại nơi sở hữu tài nguyên khi đọc/ghi tệp thật. Các stream trong ví dụ là bộ nhớ; chúng giúp tập trung kiểm tra dữ liệu mà không tạo tệp bên ngoài.

`loadFromXML` là API riêng có quy tắc riêng, trong đó phương thức đóng input stream được truyền vào. Không suy một quy tắc đóng chung chỉ từ việc mọi phương thức đều thuộc Properties.

### 9.3. XML không dùng cùng đường đọc với định dạng dòng

Properties có loadFromXML/storeToXML để đọc/ghi định dạng XML thuộc tính của Java. `storeToXML` không chỉ là store rồi đổi đuôi tệp; overload mặc định dùng UTF-8.

Nếu hệ thống cũ đang dùng XML, giữ đúng cặp API và hợp đồng encoding tương ứng. Không nạp XML bằng load thông thường rồi kỳ vọng một bộ phân tích XML sẽ xuất hiện.

### 9.4. Save là một API deprecated cụ thể

Properties.save là phương thức cũ có thể che IOException; store là đường được tài liệu ưu tiên khi cần nhận lỗi ghi.

Điều cần sửa trong mã đời cũ có thể là chọn API báo lỗi đúng, không phải thay toàn bộ lớp Properties bằng một HashMap rồi mất chức năng định dạng, defaults và I/O.

## 10. Chuyển dần sang mã hiện đại mà giữ đúng ý nghĩa

### 10.1. Tách ranh giới tương thích với mô hình sử dụng bên trong

Nếu một thư viện cũ yêu cầu Dictionary, có thể cần tiếp tục truyền một đối tượng phù hợp ở ranh giới ấy. Bên trong ứng dụng mới, khai báo theo Map khi đó là hợp đồng thật sự cần dùng.

Không ép một Map bất kỳ sang Dictionary chỉ để qua trình biên dịch. Không coi bản sao là liên kết trực tiếp hoặc coi liên kết trực tiếp là một bản sao cách ly.

Nếu sửa chữ ký API công khai, cần xem các bên gọi và yêu cầu tương thích hiện có. Một thay đổi cấu trúc dữ liệu có thể ảnh hưởng nhiều hơn vài dòng khởi tạo.

### 10.2. Chọn cấu trúc theo yêu cầu, không theo tuổi đời tên lớp

| Nhu cầu | Hướng cần đánh giá |
| --- | --- |
| Ánh xạ thông thường không cần truy cập sửa đồng thời | Một Map phù hợp, thường bắt đầu đánh giá HashMap |
| Ánh xạ được nhiều luồng cập nhật | Cơ chế đồng bộ hoặc ConcurrentMap phù hợp với từng thao tác |
| Một chuỗi cập nhật nhiều bước hoặc nhiều khóa | Bất biến nghiệp vụ và phạm vi bảo vệ trọn chuỗi |
| Giao tiếp với API yêu cầu Dictionary | Ranh giới thích nghi có hợp đồng rõ |
| Nạp/lưu cấu hình chuỗi chuẩn Java | Properties vẫn có vai trò cụ thể |
| Đọc cấu hình vào logic nghiệp vụ | Phân tích, kiểm tra rồi chuyển thành mô hình có kiểu |

Đừng thay Hashtable bằng HashMap nếu mã đang dựa vào đồng bộ mà chưa thiết kế lại chỗ truy cập.

Ngược lại, không giữ Hashtable chỉ vì “đã thread-safe” khi ứng dụng cần khả năng cập nhật đồng thời với mức tranh chấp khác. Hãy đọc hợp đồng và đo tải thực tế nếu hiệu năng là yêu cầu.

### 10.3. Với cấu hình, kiểm tra giá trị trước khi dùng

`getProperty` trả String, không tự xác nhận chuỗi là số, nằm trong phạm vi cho phép hay là một tùy chọn hợp lệ.

Một giá trị dự phòng chỉ xử lý trường hợp không tìm được thuộc tính phù hợp; nó không biến một chuỗi sai như tên cổng không phải số thành một giá trị đã hợp lệ.

Hãy xác định giá trị bắt buộc, giá trị rỗng, khoảng trắng, lỗi phân tích và miền cho phép tại ranh giới nạp cấu hình. Sau đó truyền kiểu dữ liệu phù hợp vào phần nghiệp vụ.

Không tùy tiện gọi toString lên mọi Object sai kiểu để “sửa” Properties. Cách đó có thể che nguồn dữ liệu sai và làm mất ý nghĩa xác thực cấu hình.

### 10.4. Properties có hợp đồng đồng thời và iterator riêng

API Java 17 mô tả Properties là thread-safe. Điều đó không có nghĩa nhiều lần đọc các khóa liên quan luôn là một ảnh chụp cùng phiên bản, hoặc cả chuỗi defaults được khóa như một giao dịch.

Đặc biệt, tài liệu của Properties mô tả iterator ở collection view khác Hashtable: không áp máy móc kết luận mọi iterator Properties phải ném ConcurrentModificationException khi có thay đổi.

Việc cần một cấu hình nhất quán để thực hiện một yêu cầu nghiệp vụ nên được giải quyết bằng quy trình nạp, kiểm tra và công bố cấu hình phù hợp.

Quan hệ kế thừa trong API không bảo đảm mọi chi tiết tổ chức lưu trữ, tham số hiệu năng hay cách duyệt giống lớp cha.

## 11. Lỗi thường gặp và cách đọc lại yêu cầu

| Cách hiểu hoặc sửa | Điều bị bỏ sót |
| --- | --- |
| Dictionary là interface Map đời cũ | Nó là lớp trừu tượng và không tự khai báo Map |
| Đổi kiểu biến từ Hashtable sang Map là đổi triển khai | Đối tượng thực tế và chính sách của nó vẫn còn |
| new HashMap là một view của bảng cũ | Đó là bảng mới chứa bản sao ánh xạ |
| Hashtable.contains tìm khóa | Phương thức cũ này tìm value |
| Hashtable đồng bộ nên get rồi put là một lần tăng nguyên tử | Hai lời gọi có thể bị chen giữa |
| Enumeration không ném lỗi nên an toàn khi sửa bảng | Không fail-fast không tạo hợp đồng ảnh chụp hay an toàn đồng thời |
| Properties là Map<String,String> được bảo vệ kiểu hoàn toàn | Nó kế thừa API Object–Object và có thể bị đưa sai kiểu |
| `getProperty` luôn giống get rồi ép String | Còn có defaults và xử lý giá trị không phải String |
| `containsKey`/size tính cả defaults | Chúng phản ánh phần ánh xạ trực tiếp |
| `store` tự ghi cả defaults | Cần chủ động làm phẳng nếu muốn lưu cấu hình hiệu lực |
| `load`(InputStream) tự dùng UTF-8 hiện hành | Overload này có quy tắc ISO-8859-1 riêng |
| Dấu nháy trong properties hoạt động như JSON | Chúng có thể là ký tự của chính giá trị |
| `load` lần hai thay sạch lần một | Các khóa không được đọc lại có thể còn nguyên |
| `load`/store giữ nguyên tệp do con người định dạng | Đây là mô hình dữ liệu thuộc tính, không phải trình chỉnh sửa bảo toàn văn bản |
| Legacy nghĩa tất cả API đều @Deprecated | Phải xem từng lớp, từng phương thức cụ thể |

## 12. Bài tập tự kiểm tra

### Bài 1. Quan hệ kiểu có tạo bản sao không?

Một Hashtable được gán cho cả biến Dictionary và Map. `put` qua một biến có được nhìn thấy qua biến kia không?

**Gợi ý trả lời:** Có nếu chúng cùng trỏ tới đối tượng ấy. Việc gán tham chiếu không tạo bảng mới.

### Bài 2. `contains` đang tìm gì?

Hashtable có "name" → "Lan". `contains`("name") có nghĩa cùng với containsKey("name") không?

**Gợi ý trả lời:** Không. `contains` tìm value; containsKey tìm khóa. Trong dữ liệu này contains("name") là false còn containsKey("name") là true.

### Bài 3. Hai lần tăng còn một là lỗi ở đâu?

Hai luồng cùng get 0 rồi mỗi luồng put 1 vào Hashtable. Vì sao đồng bộ từng phương thức không ngăn kết quả cuối bằng 1?

**Gợi ý trả lời:** Ý định đọc–tăng–ghi nằm ở nhiều lời gọi. Phải bảo vệ cả chuỗi hoặc dùng thao tác cập nhật phù hợp của triển khai.

### Bài 4. Defaults có được chép vào size không?

Một Properties mới chỉ có defaults chứa ba tên, chưa setProperty trực tiếp tên nào. `size` và số tên stringPropertyNames có buộc bằng nhau không?

**Gợi ý trả lời:** Không. `size` chỉ phản ánh phần ánh xạ trực tiếp; tập tên chuỗi có xét defaults.

### Bài 5. Xóa phần ghi đè nghĩa là xóa cấu hình?

Defaults có mode=safe, lớp hiện tại có mode=fast. `remove`("mode") ở lớp hiện tại làm getProperty("mode") trả gì?

**Gợi ý trả lời:** Chuỗi safe, vì phần ghi đè đã mất và giá trị dự phòng lại được tìm thấy.

### Bài 6. Integer trong Properties có an toàn không?

`put`("port", 8080) biên dịch được. Có nên kết luận mọi API đọc/lưu Properties sẽ chấp nhận dữ liệu ấy không?

**Gợi ý trả lời:** Không. Thuộc tính cần tên và giá trị String; getProperty không phải phép chuyển Object thành String và store có thể từ chối phần tử sai kiểu.

### Bài 7. Tệp UTF-8 tiếng Việt nên đi qua đường nào?

Dữ liệu byte thực sự là UTF-8. `load`(InputStream) có tự dùng đúng UTF-8 không?

**Gợi ý trả lời:** Không. Tạo Reader với UTF-8 rõ ràng rồi dùng load(Reader), hoặc dùng đúng định dạng byte/escape của API byte nếu đó là hợp đồng tệp.

### Bài 8. Nạp hai lần có giữ khóa cũ không?

Lần một nạp a=1 và b=2. Lần hai nạp riêng a=9 vào cùng đối tượng. B có tự mất không?

**Gợi ý trả lời:** Không. A được ghi đè; b còn nếu không có thao tác xóa hay chính sách thay toàn bộ khác.

### Bài 9. Lưu rồi đọc lại có giữ defaults không?

Một đối tượng chỉ có phần ghi đè cục bộ, còn host nằm trong defaults. `store` rồi load vào Properties mới không có defaults có tự phục hồi host không?

**Gợi ý trả lời:** Không. Nếu muốn tệp đầy đủ, cần chủ động tạo dữ liệu chứa các giá trị hiệu lực để lưu.

### Bài 10. Đổi Hashtable thành ConcurrentHashMap đã đủ chưa?

Đoạn mã vẫn thực hiện get rồi put để tăng bộ đếm. Chỉ đổi lớp khởi tạo có bảo đảm không mất cập nhật không?

**Gợi ý trả lời:** Không. Cần chọn đúng thao tác nguyên tử hoặc mô hình bảo vệ phù hợp với toàn bộ ý định cập nhật.

## 13. Tài liệu đối chiếu

- [Dictionary — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Dictionary.html): lớp trừu tượng cũ và định hướng dùng Map cho triển khai mới.
- [Hashtable — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Hashtable.html): null, đồng bộ, contains và các hợp đồng duyệt.
- [Enumeration — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Enumeration.html): hasMoreElements, nextElement và asIterator.
- [Properties — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html): API chuỗi, defaults, định dạng dòng, encoding, I/O và iterator.
- [ConcurrentHashMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): thao tác cập nhật đồng thời và giới hạn của kết luận nguyên tử.
- [Files — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): tạo Reader/Writer theo Charset.
- [Hashtable.java — OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Hashtable.java): đối chiếu các phương thức đồng bộ của triển khai được nêu.
- [Properties.java — OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Properties.java): đối chiếu đường getProperty và dữ liệu chuỗi. Chi tiết triển khai cần được gắn với phiên bản, không thay hợp đồng API.
