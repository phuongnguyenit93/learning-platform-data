# Import không tự động bao gồm package con trong Java

## 1. Quy tắc chính: mỗi package là một không gian tên riêng

Trong Java, **package** dùng để nhóm các kiểu có liên quan và tạo không gian tên. Dấu chấm trong tên package biểu diễn cấu trúc đặt tên, nhưng **không tạo ra quan hệ kế thừa hoặc quan hệ “import lan truyền”** giữa package cha và package con.

Ví dụ:

- `java.util` và `java.util.concurrent` là **hai package khác nhau**.
- `java.util.concurrent` và `java.util.concurrent.atomic` cũng là **hai package khác nhau**.
- `java.lang` và `java.lang.reflect` là **hai package khác nhau**.

Khi viết:

```java
import java.util.*;
```

trình biên dịch có thể phân giải tên đơn giản của các **kiểu truy cập được được khai báo trực tiếp trong package `java.util`**, chẳng hạn `List`, `ArrayList`, `Map` và `Scanner`. Nhưng câu lệnh đó **không tự động import các kiểu trong package con `java.util.concurrent`** như `TimeUnit` hay `ExecutorService`, và cũng không import `AtomicInteger` từ `java.util.concurrent.atomic`.

**Quy tắc cần nhớ:** `import p.*;` không có nghĩa “import `p` và tất cả package con”. Ký tự `*` ở đây **không phải dấu wildcard tìm kiếm thư mục đệ quy**.

## 2. Ví dụ: `java.util.*` không tự đưa `TimeUnit` vào scope

Xét mã nguồn:

```java
import java.util.*;

class Example {
    void demo() {
        List<String> words = new ArrayList<>(); // Hợp lệ
        // TimeUnit.SECONDS.toMillis(2);       // LỖI: thiếu import cho TimeUnit
    }
}
```

`List` và `ArrayList` thuộc chính package `java.util`. Còn `TimeUnit` thuộc `java.util.concurrent`, nên lệnh `import java.util.*;` không giúp tên `TimeUnit` được nhận diện.

Có hai cách xử lý đúng.

**Cách 1 — Import kiểu trực tiếp:**

```java
import java.util.*;
import java.util.concurrent.TimeUnit;

// Trong phương thức:
long millis = TimeUnit.SECONDS.toMillis(2); // 2000
```

**Cách 2 — Dùng tên đầy đủ, không cần thêm import:**

```java
import java.util.*;

// Trong phương thức:
long millis = java.util.concurrent.TimeUnit.SECONDS.toMillis(2); // 2000
```

Các đoạn này là **mã minh họa**, chưa phải chương trình độc lập. Nếu cần nhiều kiểu trong cùng package con, có thể dùng:

```java
import java.util.concurrent.*;
```

Lệnh đó có thể giúp dùng `TimeUnit` và `ExecutorService` bằng tên ngắn, nhưng **vẫn không tự import `java.util.concurrent.atomic.AtomicInteger`** hoặc các kiểu trong những package con khác của `java.util.concurrent`.

## 3. Một số ví dụ phổ biến khác

| Đã import | Kiểu dùng được bằng tên ngắn nhờ import đó | Kiểu **không** được tự import |
| --- | --- | --- |
| `import java.util.*;` | `List`, `ArrayList`, `Map` | `java.util.concurrent.TimeUnit` |
| `import java.util.concurrent.*;` | `TimeUnit`, `ExecutorService` | `java.util.concurrent.atomic.AtomicInteger` |
| `import java.security.*;` | `MessageDigest`, `SecureRandom`, `KeyPair` | `java.security.cert.Certificate` |
| `import java.nio.file.*;` | `Path`, `Files` | `java.nio.file.attribute.BasicFileAttributes` |
| Import ngầm `java.lang.*` | `String`, `System`, `Math`, `Integer` | `java.lang.reflect.Method`, `java.lang.invoke.MethodHandles` |

Ví dụ cụ thể với reflection:

```java
// String dùng trực tiếp do thuộc java.lang:
String text = "Java";

// Method thuộc package java.lang.reflect, không tự thành tên ngắn:
// Method m = String.class.getMethod("length"); // LỖI nếu chưa import Method

java.lang.reflect.Method m = String.class.getMethod("length");
```

Đoạn minh họa cuối cần nằm trong phương thức có khai báo `throws NoSuchMethodException` hoặc xử lý ngoại lệ thích hợp. Có thể thay tên đầy đủ bằng khai báo `import java.lang.reflect.Method;` ở đầu file. Điểm mấu chốt: **import ngầm `java.lang` cũng không lan xuống package con**.

Các package chuẩn này có thể nằm trong cùng một module (chẳng hạn `java.base`), nhưng cùng module **không khiến import tự lan sang các package khác**.

## 4. Chương trình Java 17+ hoàn chỉnh

Ví dụ dưới đây minh họa đồng thời **on-demand import ở package cha**, **import tường minh từ package con**, và **tên đầy đủ thay cho import**.

Tạo tệp **`src/lesson/ImportSubpackageDemo.java`** với nội dung:

```java
package lesson;

import java.util.*;
import java.util.concurrent.TimeUnit;
import java.lang.reflect.Method;

public class ImportSubpackageDemo {
    public static void main(String[] args)
            throws NoSuchMethodException {

        // ArrayList, List và Map trực tiếp thuộc java.util.
        List<String> words = new ArrayList<>();
        words.add("Java");
        words.add("core");
        System.out.println("Words: " + words);

        // TimeUnit thuộc java.util.concurrent:
        // cần import riêng dù đã có java.util.*.
        long millis = TimeUnit.SECONDS.toMillis(3);
        System.out.println("Millis: " + millis);

        // AtomicInteger ở package con khác,
        // ở đây dùng tên đầy đủ thay vì import.
        java.util.concurrent.atomic.AtomicInteger counter =
                new java.util.concurrent.atomic.AtomicInteger(4);
        System.out.println("Counter: " + counter.addAndGet(2));

        // String thuộc java.lang, được import ngầm định.
        String name = "Java";
        System.out.println("Name: " + name);

        // Method thuộc java.lang.reflect;
        // cần import riêng ở đầu tệp.
        Method method = String.class.getMethod("substring", int.class);
        System.out.println("Method: " + method.getName());

        // Entry là kiểu thành viên lồng trong Map, KHÔNG phải package con.
        Map.Entry<String, Integer> entry = Map.entry("id", 7);
        System.out.println("Entry: "
                + entry.getKey() + "=" + entry.getValue());
    }
}
```

Đứng ở thư mục chứa `src`, với **JDK 17 trở lên**. **Trước lần đầu chạy lệnh `javac -d out`, phải tạo thư mục `out`**: Bash/Linux/macOS chạy `mkdir -p out`; PowerShell chạy `New-Item -ItemType Directory -Force out | Out-Null` (CMD: `if not exist out mkdir out`). Khi `out` đã tồn tại, biên dịch và chạy trên Windows PowerShell/CMD hoặc Linux/macOS:

```bash
javac -encoding UTF-8 -d out src/lesson/ImportSubpackageDemo.java
java -cp out lesson.ImportSubpackageDemo
```

`-d out` để `javac` sinh cấu trúc thư mục cho các file `.class` theo package; `lesson.ImportSubpackageDemo` là tên đầy đủ của lớp chứa `main`.

**Stdout chính xác** (lệnh `javac` thành công không in dòng nào):

```text
Words: [Java, core]
Millis: 3000
Counter: 6
Name: Java
Method: substring
Entry: id=7
```

**Giải thích kết quả:**

1. `List`, `ArrayList`, `Map` nhận diện được nhờ `import java.util.*;`.
2. `TimeUnit` được nhận diện nhờ `import java.util.concurrent.TimeUnit;`, không phải nhờ wildcard ở `java.util`.
3. `AtomicInteger` dùng **tên đầy đủ** `java.util.concurrent.atomic.AtomicInteger`, nên không cần import riêng.
4. `String` được dùng nhờ import ngầm của `java.lang`, còn `Method` cần import riêng từ `java.lang.reflect`.
5. `Map.Entry` là **kiểu lồng nhau** (member type) bên trong `Map`, không phải lớp thuộc một package tên `java.util.Map`.

Không cần thêm `import java.util.concurrent.*;` vào ví dụ vì một kiểu `TimeUnit` đã được import cụ thể, còn `AtomicInteger` đang được gọi bằng tên đầy đủ. Cách trình bày đó giúp nhìn thấy chính xác sự khác nhau giữa ba cơ chế.

## 5. Khác nhau giữa package con và kiểu lồng nhau

Dấu chấm trong tên Java có thể xuất hiện ở **tên package** hoặc ở **tên của kiểu thành viên**. Đó là hai cấu trúc khác nhau.

**Package con:**

```java
java.util.concurrent.TimeUnit
```

Ở đây `java.util.concurrent` là package chứa lớp `TimeUnit`. Nó không được import bởi `import java.util.*;`.

**Kiểu lồng nhau:**

```java
java.util.Map.Entry
```

Ở đây `Map` là interface thuộc `java.util`, còn `Entry` là một interface thành viên lồng trong `Map`. Có thể viết:

```java
import java.util.Map;

// Trong phương thức:
Map.Entry<String, Integer> item = Map.entry("key", 10);
```

Hoặc import trực tiếp kiểu thành viên:

```java
import java.util.Map.Entry;

// Trong phương thức:
Entry<String, Integer> item = java.util.Map.entry("key", 10);
```

Đặc biệt, `import java.util.Map.*;` là một dạng **type-import-on-demand** cho các kiểu thành viên truy cập được của `Map` — hoàn toàn khác `import java.util.*;`, vốn chọn các kiểu top-level từ package `java.util`. Không nên nhầm dấu chấm giữa `Map` và `Entry` với một package con của `java.util`.

Khi đọc một tên nhiều thành phần, hãy xác định rõ mỗi thành phần là **package, kiểu top-level hay kiểu thành viên**, thay vì phỏng đoán mọi đoạn giữa các dấu chấm là cấp thư mục.

## 6. Không có kế thừa quyền truy cập giữa package cha và package con

Quan hệ tên `com.example` và `com.example.feature` **không tạo quan hệ truy cập nội bộ**. Một thành viên hoặc lớp top-level có quyền truy cập **package-private** (không ghi access modifier) chỉ truy cập được từ code thuộc **đúng cùng package**, không tự mở cho mã ở package có cùng tiền tố.

Ví dụ hai tệp minh họa:

**`src/com/example/Helper.java`**

```java
package com.example;

class Helper {
    static void ping() {
        System.out.println("ping");
    }
}
```

**`src/com/example/feature/Feature.java`**

```java
package com.example.feature;

// import com.example.Helper; // LỖI: Helper không public

public class Feature {
    public static void main(String[] args) {
        // com.example.Helper.ping(); // LỖI truy cập
        System.out.println("Feature");
    }
}
```

Đây là ví dụ **giải thích quyền truy cập**, tách biệt chương trình ở mục 4. Kể cả khi viết tên đầy đủ `com.example.Helper`, quy tắc package-private vẫn ngăn lớp `Feature` truy cập. `import` hay việc đặt thư mục bên trong `com/example` **không thay đổi access modifiers**.

Nếu cần sử dụng từ package khác, kiểu được công khai theo thiết kế phù hợp (thường `public`) và các thành viên cần gọi cũng phải có khả năng truy cập tương ứng.

## 7. Cách tự kiểm tra khi trình biên dịch báo không nhận tên

Một tình huống phổ biến là đã viết `import java.util.*;` nhưng `TimeUnit` vẫn bị báo không tìm thấy. Kiểm tra theo thứ tự:

1. **Xác định tên đầy đủ thật sự của kiểu:** `TimeUnit` là `java.util.concurrent.TimeUnit`, không phải `java.util.TimeUnit`.
2. **Kiểm tra import đúng package:** viết `import java.util.concurrent.TimeUnit;` hoặc `import java.util.concurrent.*;`, không chỉ `import java.util.*;`.
3. **Thử tên đầy đủ tại nơi dùng:** `java.util.concurrent.TimeUnit.SECONDS.toMillis(3)`. Nếu hợp lệ, vấn đề có thể là tra cứu tên/import.
4. **Xem quyền truy cập:** lớp/thành viên có truy cập được từ package hiện tại không? Import không bỏ qua quy tắc truy cập.
5. **Kiểm tra classpath hoặc module path nếu là thư viện ngoài:** import chỉ giải quyết tên, không tải thư viện về hay bổ sung đường dẫn. Với hệ thống module, cần các quan hệ đọc/export thích hợp.
6. **Không thêm import chỉ để che giấu xung đột:** khi có hai kiểu tên đơn giản trùng nhau từ các package khác nhau, dùng single-type import phù hợp hoặc tên đầy đủ.

**Ví dụ lỗi có chủ ý** (không phải chương trình độc lập để chạy):

```java
import java.util.*;

// Trong phương thức:
// TimeUnit.SECONDS.toMillis(1); // Thiếu import java.util.concurrent.TimeUnit
// AtomicInteger n = new AtomicInteger(0); // Thiếu import java.util.concurrent.atomic.AtomicInteger
```

Không cần ghi nhớ tên mọi package, nhưng cần tra cứu đúng **package khai báo trực tiếp kiểu** thay vì suy diễn từ tiền tố.

## 8. Các lỗi và ngộ nhận thường gặp

| Ngộ nhận | Kết luận đúng |
| --- | --- |
| “`import a.b.*;` tự import luôn `a.b.c.*;`.” | **Sai.** Mỗi package là không gian tên riêng; wildcard không đệ quy. |
| “`java.lang` được import ngầm nên `java.lang.reflect.Method` cũng được import.” | **Sai.** Package con không được tự import. |
| “`import java.util.concurrent.*;` nhận luôn `AtomicInteger`.” | **Sai.** `AtomicInteger` ở `java.util.concurrent.atomic`. |
| “Viết tên đầy đủ vẫn cần thêm `import`.” | **Sai.** Tên đầy đủ giúp tham chiếu trực tiếp tới kiểu mà không cần import kiểu đó. |
| “`Map.Entry` là package con của `Map`.” | **Sai.** `Entry` là kiểu thành viên lồng trong `Map`. |
| “Package `com.example.sub` truy cập được mọi thành viên package-private trong `com.example`.” | **Sai.** Hai package là khác nhau. |
| “`import` đưa tất cả lớp vào bộ nhớ trước khi chạy.” | **Sai.** Import là cơ chế phân giải tên lúc biên dịch, không tự khởi tạo toàn bộ lớp. |
| “Có `import` là không cần dependency/classpath nữa.” | **Sai.** Trình biên dịch/JVM vẫn phải tìm được định nghĩa kiểu có thể truy cập. |

**Ghi nhớ:** `import package.*` chỉ liên quan tới các kiểu thích hợp **trực tiếp trong package đó**; nó không tự bao gồm các package con có cùng tiền tố. Muốn dùng kiểu thuộc package con, hãy **import đúng package con/kiểu** hoặc **viết tên đầy đủ của kiểu**.