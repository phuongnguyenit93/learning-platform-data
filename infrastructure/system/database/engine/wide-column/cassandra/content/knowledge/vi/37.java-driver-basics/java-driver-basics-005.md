# Driver configuration, execution profile và giá trị có hiệu lực trong Java Driver Cassandra

> **Chương:** Java driver cơ bản  
> **Phạm vi:** Cấu hình Apache Cassandra Java Driver 4.x cho ứng dụng Java thông qua HOCON, `DriverConfigLoader`, default/named execution profiles và thuộc tính của từng statement; cách xác minh **giá trị thực sự có hiệu lực** ở thời điểm gọi CQL, hiểu ưu tiên nhiều lớp, hot reload, tính bất biến của statement và các rủi ro production. Ví dụ API bám sát Java Driver 4.17; từ 4.18, dự án Java Driver được Apache Software Foundation duy trì, nên luôn đối chiếu tài liệu của phiên bản và artifact thực dùng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **`DriverConfigLoader`**, `DriverConfig`, `DriverExecutionProfile`, `reference.conf`, `application.conf`, system properties và programmatic overrides.
2. Đọc đúng thứ tự ưu tiên giữa các **nguồn cấu hình**, giữa **default và named profile**, và giữa **profile và explicit statement settings**.
3. Tạo các execution profile cho **point lookup, range/paged read và thao tác quản trị** với timeout, consistency, page size và idempotence khác nhau.
4. Phân biệt **giá trị khai báo**, **giá trị đã hợp nhất (resolved)** và **giá trị cuối cùng mà request dùng**, kể cả trường hợp hot reload.
5. Truy vấn typed getters của `session.getContext().getConfig()`, xác minh profile đang tồn tại, tìm các override từ JVM và nhận diện cấu hình không được reload.
6. Viết ứng dụng Java 17 dùng `CqlSession`, `SimpleStatement`/`PreparedStatement`/`BoundStatement` và named profile đúng API 4.x.
7. Đặt `local-datacenter`, contact points, CL, request timeout, serial consistency, paging và idempotence phù hợp replication và mục tiêu nghiệp vụ.
8. Thực hiện kiểm thử CQL + Java trên cluster lab, so sánh default/profile/request override, rồi chạy một thay đổi có kiểm soát và xác minh rollback.

**Ngữ cảnh:** Dịch vụ `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` yêu cầu hiểu kiến trúc phân tán và mô hình wide-column, khóa phân vùng, bảng thiết kế theo truy vấn, consistency đọc/ghi và kết nối từ Java. Driver configuration là **lớp điều khiển hành vi request của client**, nhưng nó không thay thế thiết kế partition key, replica placement, compaction/repair hay dữ liệu thực trong Cassandra.

## 2. Bốn lớp cần phân biệt khi nói “giá trị có hiệu lực”

Một request có thể chịu ảnh hưởng của nhiều lớp:

~~~text
                      JAVA APPLICATION
                             |
                 CqlSession / DriverContext
                             |
                 DRIVER CONFIG LOADER
         +-------------------+-------------------+
         |                   |                   |
   reference.conf     application.conf      system properties
    defaults             overrides          (+ programmatic)
         +-------------------+-------------------+
                             |
                      DEFAULT PROFILE
                             |
                 NAMED PROFILE (nếu chọn)
                   kế thừa + override
                             |
                 STATEMENT-LEVEL OPTIONS
                   giá trị tường minh
                             |
                     EFFECTIVE REQUEST
              timeout / CL / page / idempotence
                             |
                 COORDINATOR -> REPLICAS
~~~

Phải hỏi chính xác:

1. **Declared value:** Giá trị nào có trong một file hoặc property?
2. **Resolved config value:** Sau merge/fallback, `DriverExecutionProfile` trả gì?
3. **Selected profile:** Request thực sự dùng `default` hay một named/derived profile?
4. **Explicit statement value:** Một `setTimeout` hoặc `setConsistencyLevel` trên statement có ghi đè profile không?
5. **Runtime behavior:** Config và statement đã chọn có thực sự dẫn tới request thành công dưới RF/DC, trạng thái node và workload hiện tại không?

Ví dụ: file `application.conf` khai báo `basic.request.timeout = 2 seconds`; named profile `reporting` đặt 8 giây; statement đó gọi `setTimeout(Duration.ofSeconds(1))`. **Request này dùng timeout 1 giây**, không phải 2 hoặc 8. Nhưng nó không bảo đảm truy vấn hoàn tất trong 1 giây hoặc server ngừng công việc chính xác tại mốc đó: timeout là ngân sách phía driver, còn cancellation/đã ghi hay chưa cần hiểu riêng.

### 2.1. Giá trị cuối cùng không đồng nghĩa kết quả nghiệp vụ

| Giá trị đã xác nhận | Điều nó chứng minh | Điều nó **không** chứng minh |
|---|---|---|
| `REQUEST_CONSISTENCY=LOCAL_QUORUM` | Client sẽ yêu cầu mức nhất quán ấy trên request không override | Replica dữ liệu chắc chắn cùng đúng hoặc mọi DC đã đồng bộ |
| `REQUEST_TIMEOUT=2s` | Giới hạn thời gian client đặt cho request | Cassandra đã hoàn tác một write timeout |
| `REQUEST_PAGE_SIZE=100` | Cỡ trang gợi ý cho lần fetch | Query chỉ đọc tổng cộng 100 rows |
| `REQUEST_DEFAULT_IDEMPOTENCE=false` | Nếu statement không khai báo, driver mặc định xem không idempotent | Mutation thật sự không idempotent ở mức nghiệp vụ |
| `local-datacenter=dc1` | Driver nhận diện DC cục bộ cho routing/policy | Máy chủ dc1 đang khỏe hoặc đã có dữ liệu |

Do đó công việc “đọc effective config” khác công việc “đo p99/errors” và “đối chiếu dữ liệu”: cả ba đều cần khi đánh giá production.

## 3. Các thành phần trong cấu hình Java Driver 4.x

### 3.1. Cây cấu hình

Java Driver 4.x dùng **Typesafe Config / HOCON** với root mặc định `datastax-java-driver`:

~~~hocon
datastax-java-driver {
  basic {
    session-name = "order-api"

    contact-points = [ "127.0.0.1:9042" ]

    load-balancing-policy {
      local-datacenter = "datacenter1"
    }

    request {
      timeout = 2 seconds
      consistency = LOCAL_ONE
      serial-consistency = SERIAL
      page-size = 5000
      default-idempotence = false
    }
  }

  profiles {
    point_read {
      basic.request.timeout = 500 milliseconds
      basic.request.page-size = 50
    }
  }
}
~~~

Đây là **cấu hình mẫu** minh họa API 4.x, không khuyến nghị dùng `LOCAL_ONE` và timeout 500 ms cho mọi hệ thống. Contact point và `local-datacenter` trong ví dụ chỉ khớp lab nếu node thực sự thuộc DC `datacenter1`; production thay bằng hostname/IP/DC thật.

### 3.2. Vai trò của từng phần

| Thành phần | Vai trò | Có thể hiểu nhầm thành |
|---|---|---|
| `reference.conf` | Cấu hình mặc định đóng gói trong driver JAR và dependencies | “File cần sửa trực tiếp” — **không nên** |
| `application.conf` | Overrides thuộc ứng dụng trên classpath | “Tự động thắng mọi nguồn” — **không phải** |
| JVM system properties | Override nhanh bằng `-Ddatastax-java-driver...` | “Biến môi trường OS bất kỳ tự ánh xạ” — **không** |
| `DriverConfigLoader` | Chọn nguồn, hợp nhất và có thể reload config | Một profile hoặc object cấu hình bất biến duy nhất |
| `DriverConfig` | API quan sát các profiles đã resolve | Toàn bộ lịch sử file config |
| Default profile | Fallback cho request không chọn named profile | Một profile phải khai báo bằng tên `default` trong file |
| Named profile | Nhóm overrides cho kiểu request | Một `CqlSession`/connection pool mới độc lập |
| Derived profile | Bản sao có chọn lọc từ profile tồn tại | Một profile cần tạo mới trên mỗi request |
| Statement attributes | Overrides trên đúng request | Thay đổi config global cho các request khác |

**Một `CqlSession` thường được tái sử dụng**, thread-safe và quản lý resources kết nối. Không tạo một session mới cho từng execution profile hoặc từng request.

### 3.3. HOCON: cú pháp chấm và dạng lồng nhau

Hai đoạn sau tương đương về key:

~~~hocon
datastax-java-driver {
  basic.request.timeout = 2 seconds
}
~~~

~~~hocon
datastax-java-driver {
  basic {
    request {
      timeout = 2 seconds
    }
  }
}
~~~

`2 seconds` là duration, không phải chuỗi `"2"` không đơn vị; `page-size=100` là số nguyên; `consistency=LOCAL_QUORUM` là một giá trị được parser driver diễn giải. HOCON cho phép comments bằng `#`/`//` và dùng substitution, nhưng phải kiểm **giá trị cuối cùng đã resolve** thay vì suy từ text gốc.

## 4. Thứ tự ưu tiên của các nguồn config

Với default loader của Java Driver 4.17, nguồn được hợp nhất theo **thứ tự ưu tiên từ cao xuống thấp**:

| Thứ tự | Nguồn | Ví dụ |
|---:|---|---|
| 1 | **System properties** | `-Ddatastax-java-driver.basic.request.timeout="4 seconds"` |
| 2 | **Programmatic overrides** khi dùng `programmaticBuilder()` | `withDuration(REQUEST_TIMEOUT, 3s)` |
| 3 | `application.conf` trên classpath | `basic.request.timeout = 2 seconds` |
| 4 | `application.json` trên classpath | Option tương đương ở dạng JSON |
| 5 | `application.properties` trên classpath | Option dạng properties |
| 6 | `reference.conf` | Driver defaults |

Thứ tự này áp dụng cho loader dùng **programmatic overrides có fallback theo classpath**. Với `DriverConfigLoader.fromFile(file)`, chuỗi thông thường là **system properties → nội dung file chỉ định → reference.conf**, không tự trộn mọi `application.conf` khác trong classpath. Một **custom loader** có thể có cách hợp nhất riêng: không áp thứ tự trên như quy luật chung cho mọi implementation.

### 4.1. Ví dụ xung đột ba nguồn

Giả sử:

~~~hocon
# application.conf
datastax-java-driver.basic.request.timeout = 2 seconds
~~~

~~~java
// Programmatic config loader
DriverConfigLoader loader = DriverConfigLoader.programmaticBuilder()
    .withDuration(DefaultDriverOption.REQUEST_TIMEOUT,
                  Duration.ofSeconds(3))
    .build();
~~~

Và JVM chạy với:

~~~bash
java -Ddatastax-java-driver.basic.request.timeout="4 seconds" \
     -jar order-service.jar
~~~

**Resolved timeout của default profile dự kiến là 4 giây**, do system property ưu tiên hơn programmatic và file. Nếu system property bị bỏ thì còn 3 giây; nếu bỏ cả programmatic override thì còn 2 giây. **Không thể biết** giá trị chỉ bằng cách mở `application.conf`.

### 4.2. Những nguồn dễ làm người vận hành hiểu nhầm

- **Environment variables:** Java Driver không mặc định ánh xạ mọi biến như `CASSANDRA_TIMEOUT` sang `basic.request.timeout`. Framework Spring/Micronaut/Quarkus, script khởi động hoặc custom loader có thể tự ánh xạ; phải kiểm lớp tích hợp cụ thể.
- **Multiple application.conf:** Thư viện hoặc nhiều resources cùng tên có thể tham gia merge; kiểm classpath/packaging nếu giá trị bất ngờ.
- **JVM flags trong container:** Tham số từ `JAVA_TOOL_OPTIONS`/startup script có thể tạo system property mà người đọc file không thấy.
- **File trong source tree:** Chỉnh `src/main/resources/application.conf` trên máy dev không làm JAR đang chạy tự đổi; phải deploy resource mới hoặc dùng loader trỏ tới file writable.
- **Programmatic builder/session builder:** Những lựa chọn như `withLocalDatacenter` hoặc `addContactPoint` được áp trực tiếp ở quá trình tạo session; đừng suy từ text config rằng mọi hành vi session đã được thay đổi.

## 5. Default profile và named execution profiles

### 5.1. Kế thừa theo từng option

~~~hocon
datastax-java-driver {
  basic.request {
    timeout = 2 seconds
    consistency = LOCAL_QUORUM
    page-size = 500
    default-idempotence = false
  }

  profiles {
    point_read {
      basic.request.timeout = 400 milliseconds
      basic.request.page-size = 40
    }

    history_read {
      basic.request.timeout = 6 seconds
      basic.request.page-size = 200
    }
  }
}
~~~

| Option | Default | `point_read` effective | `history_read` effective |
|---|---|---|---|
| Timeout | 2 s | **400 ms** | **6 s** |
| Consistency | LOCAL_QUORUM | LOCAL_QUORUM (*kế thừa*) | LOCAL_QUORUM (*kế thừa*) |
| Page size | 500 | **40** | **200** |
| Default idempotence | false | false (*kế thừa*) | false (*kế thừa*) |

Mỗi named profile **kế thừa default** cho option không override. Ví dụ `point_read` không ghi `consistency` thì giá trị đó đến từ default **đã merge**, không tự rơi về `LOCAL_ONE` trong reference.conf nếu default đang `LOCAL_QUORUM`.

### 5.2. Profile dùng để biểu diễn chính sách cho *loại truy vấn*

| Query family | Gợi ý profile | Vì sao? |
|---|---|---|
| `orders.getById` | `point_read` | Partition lookup nhỏ, ngân sách latency ngắn |
| `orders.listRecent` | `history_read` | Có thể paging và cần timeout/page size riêng |
| `orders.placeOrder` | `write_critical` | CL/timeout/idempotency theo hợp đồng ghi |
| `schema.migrate` | `ddl` | DDL có thể chậm hơn OLTP, timeout khác |
| `export.nightly` | `batch_read` | Giới hạn total consumption và ảnh hưởng peak |

Tên profile không mang semantics kỹ thuật tự động: đặt `point_read` không khiến driver biết partition key hoặc tối ưu một CQL Filtering. Nó chỉ chọn các options đã khai báo. Truy vấn đúng shape, prepared statement và token-aware routing vẫn phải làm riêng.

### 5.3. Không coi profile là security hoặc isolation boundary

- Một named profile **không tạo keyspace/role/tenant ACL mới**.
- Nó không tự tách `CqlSession`, disk, coordinator hay replica pool hoàn toàn; một số chính sách có thể dùng instance riêng/shared tùy config.
- Profile có timeout dài không có quyền “vượt” CQL auth/network permissions.
- Profile dùng page-size nhỏ không giới hạn **tổng số rows** nếu code tiếp tục fetch mọi trang.
- Dùng các profile với CL khác nhau phải được business/data correctness review, không chỉ performance review.

## 6. Mẫu `application.conf` cho ứng dụng Java kết nối Cassandra

### 6.1. Cấu hình lab đầy đủ

Đặt một file `src/main/resources/application.conf` trong **classpath** của ứng dụng Java/Maven/Gradle:

~~~hocon
datastax-java-driver {
  basic {
    session-name = "cassandra-driver-lab"
    contact-points = [ "127.0.0.1:9042" ]

    load-balancing-policy {
      local-datacenter = "datacenter1"
    }

    config-reload-interval = 5 minutes

    request {
      timeout = 2 seconds
      consistency = LOCAL_ONE
      serial-consistency = SERIAL
      page-size = 500
      default-idempotence = false
    }
  }

  profiles {
    point_read {
      basic.request.timeout = 500 milliseconds
      basic.request.page-size = 25
      basic.request.default-idempotence = true
    }

    history_read {
      basic.request.timeout = 5 seconds
      basic.request.page-size = 100
      basic.request.default-idempotence = true
    }

    ddl {
      basic.request.timeout = 15 seconds
      basic.request.page-size = 500
    }
  }
}
~~~

**Phạm vi áp dụng của mẫu:** Cassandra lab **một node, RF=1**, DC tên `datacenter1`, query chỉ đọc trên các profile `point_read` và `history_read`. Với production nhiều DC, **không copy `LOCAL_ONE`**, contact point localhost hoặc `default-idempotence=true` sang mọi statement nếu chưa đánh giá hợp đồng nhất quán, tính idempotent của mutation và RF. Đổi tên DC thực từ `nodetool status`/topology inventory.

### 6.2. Khi chuyển sang production

Ví dụ khung khác:

~~~hocon
# Minh họa; host và local DC phải thay bằng topology thật.
datastax-java-driver {
  basic.contact-points = [
    "cassandra-1.dc1.example.internal:9042",
    "cassandra-2.dc1.example.internal:9042"
  ]

  basic.load-balancing-policy.local-datacenter = "dc1"
  basic.request {
    consistency = LOCAL_QUORUM
    timeout = 3 seconds
    page-size = 500
    default-idempotence = false
  }

  profiles {
    fast_read {
      basic.request.timeout = 800 milliseconds
      basic.request.page-size = 50
      basic.request.default-idempotence = true
    }

    report_read {
      basic.request.timeout = 8 seconds
      basic.request.page-size = 200
      basic.request.default-idempotence = true
    }
  }
}
~~~

Các mốc `800 ms`/`8 s` là **minh họa** để phân biệt SLO, không phải cấu hình được Apache khuyến cáo cho mọi hệ thống. Nếu app cần read-your-writes hoặc mức đảm bảo riêng, CL/phân vùng/RF phải được xác định theo workload, không chỉ chọn `LOCAL_QUORUM` để “trông an toàn”.

### 6.3. Local datacenter không phải một tùy chọn per-query

`local-datacenter` định hướng load balancing chính sách routing của driver và phải khớp **tên DC của cluster đích**. Tên `dc1` hay `datacenter1` là **label topology**, không phải alias tự tạo tùy ý trong config. Khi sai có thể:

- Session không khởi tạo được hoặc không tìm thấy local nodes phù hợp.
- Routing đi tới coordinator không mong muốn.
- `LOCAL_QUORUM` được đánh giá trong **local DC thực của coordinator**, không phải “toàn cluster”.
- Ứng dụng triển khai ở dc2 nhưng vẫn cấu hình dc1, tăng network latency và gây hiểu nhầm về durability/consistency.

Đọc **góc nhìn node/DC** và kiểm các kết nối thực tế. Driver config không làm thay đổi `NetworkTopologyStrategy` hoặc RF của keyspace.

## 7. Statement-level override: ưu tiên cuối cùng cho một request

Các thuộc tính có thể đặt trực tiếp trên statement gồm:

- `execution profile` (bằng tên hoặc object derived profile).
- `request timeout`.
- `normal consistency level`; serial consistency cho LWT.
- `page size` và paging state.
- `idempotent flag`.
- `tracing`, routing information hoặc query timestamp khi cần.

Với các request settings có thể override, quy tắc:

~~~text
Explicit statement option  >  selected execution profile option
                                      |
                     nếu profile không override:
                                 default profile
                                      |
                         merged config sources
~~~

**Quan trọng:** “Statement chọn `point_read`” không có nghĩa statement sẽ dùng mọi option trong `point_read`: nếu lập trình viên đặt `setTimeout` hoặc `setPageSize` sau đó, những option ấy thắng profile. Những option không cho override qua statement vẫn do config/policy quản lý.

### 7.1. Ví dụ đúng với SimpleStatement.Builder

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.time.Duration;

SimpleStatement statement = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setExecutionProfileName("point_read")
    .setTimeout(Duration.ofSeconds(1))
    .setConsistencyLevel(DefaultConsistencyLevel.ONE)
    .setIdempotent(true)
    .build();
~~~

Giả sử `point_read` có timeout 500 ms và default CL `LOCAL_ONE`, statement trên:

- Dùng profile `point_read` cho những options không bị ghi đè.
- **Timeout có hiệu lực là 1 giây** vì đặt trên statement.
- **Consistency là ONE** vì statement đặt tường minh; với query system table trong lab chỉ mang tính minh họa, không nên suy thành CL cho truy vấn nghiệp vụ.
- Idempotence tường minh là `true`, không dùng mặc định của profile.

### 7.2. Statement 4.x bất biến; không bỏ qua giá trị trả về

**Sai:**

~~~java
SimpleStatement s = SimpleStatement.newInstance(
    "SELECT release_version FROM system.local");

s.setExecutionProfileName("point_read");
s.setTimeout(Duration.ofSeconds(1));

// s vẫn là object ban đầu, không được thay đổi tại chỗ.
// session.execute(s) sẽ dùng default profile/timeout nếu không được set.
~~~

**Đúng:**

~~~java
SimpleStatement s = SimpleStatement.newInstance(
    "SELECT release_version FROM system.local");

s = s.setExecutionProfileName("point_read")
     .setTimeout(Duration.ofSeconds(1));

// session.execute(s) nhận object mới đã có các thuộc tính trên.
~~~

Các built-in statement setters trong Java Driver 4.x trả **instance mới**. Đây là một trong những nguyên nhân phổ biến khiến “đã gọi setter mà driver vẫn dùng giá trị cũ”.

### 7.3. Prepared và BoundStatement cũng cần chú ý

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.time.LocalDate;

PreparedStatement prepared = session.prepare(
    "SELECT event_time, status FROM driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ? LIMIT 50");

BoundStatement bound = prepared.bind(
    "tenant-a", LocalDate.parse("2026-11-21"));

bound = bound.setExecutionProfileName("history_read")
             .setPageSize(20);

// effective page-size=20 cho request này,
// không phải page-size=100 của history_read.
session.execute(bound);
~~~

`PreparedStatement` giúp bind types/routing key ổn định nhưng không ngăn statement-level override. **Một query được prepare nhiều lần không cần mỗi lần tạo session**; chuẩn bị lại trong hot path có thể gây overhead.

### 7.4. Bảng đối chiếu precedence tổng hợp

Giả định `application.conf` chứa:

~~~hocon
datastax-java-driver {
  basic.request.timeout = 2 seconds
  basic.request.page-size = 500
  profiles {
    history_read {
      basic.request.timeout = 5 seconds
      basic.request.page-size = 100
    }
  }
}
~~~

| Lệnh Java | Timeout hiệu lực | Page size hiệu lực |
|---|---|---|
| `execute(SimpleStatement.newInstance(...))` | 2 s | 500 |
| `setExecutionProfileName("history_read")` | 5 s | 100 |
| `history_read` + `setTimeout(1s)` | **1 s** | 100 |
| `history_read` + `setPageSize(20)` | 5 s | **20** |
| `history_read` + cả hai overrides | **1 s** | **20** |

Nếu JVM có `-Ddatastax-java-driver.basic.request.timeout="7 seconds"`, nó đổi **default resolved timeout thành 7 s**, nhưng `history_read` vẫn có override riêng 5 s (nếu không có system property **nhắm đúng path của named profile**). Statement đặt 1 s vẫn là 1 s.

## 8. Đọc `DriverConfig` và effective profile values bằng Java

### 8.1. API quan sát cấu hình đã hợp nhất

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfig;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import java.time.Duration;

public final class DriverEffectiveConfig {
    private DriverEffectiveConfig() {}

    public static void print(CqlSession session) {
        DriverConfig config = session.getContext().getConfig();

        DriverExecutionProfile defaultProfile =
            config.getDefaultProfile();
        DriverExecutionProfile pointRead =
            config.getProfile("point_read");
        DriverExecutionProfile historyRead =
            config.getProfile("history_read");

        logProfile(defaultProfile);
        logProfile(pointRead);
        logProfile(historyRead);
    }

    private static void logProfile(DriverExecutionProfile profile) {
        Duration timeout = profile.getDuration(
            DefaultDriverOption.REQUEST_TIMEOUT);

        String cl = profile.getString(
            DefaultDriverOption.REQUEST_CONSISTENCY);

        String serialCl = profile.getString(
            DefaultDriverOption.REQUEST_SERIAL_CONSISTENCY);

        int pageSize = profile.getInt(
            DefaultDriverOption.REQUEST_PAGE_SIZE);

        boolean defaultIdempotence = profile.getBoolean(
            DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE);

        System.out.printf(
            "profile=%s timeout=%s CL=%s serialCL=%s " +
            "pageSize=%d defaultIdempotence=%s%n",
            profile.getName(),
            timeout, cl, serialCl, pageSize, defaultIdempotence);
    }
}
~~~

Đây là **cách mạnh nhất để biết giá trị profile đã resolve trong session hiện tại**, thay vì giả định từ một file. API `DriverConfig.getProfile(name)` ném `IllegalArgumentException` khi profile không tồn tại; nên kiểm trong startup/tests, không đợi production traffic mới phát hiện lỗi gõ tên.

### 8.2. Đọc `DriverExecutionProfile` không tự tính explicit overrides

Nếu `point_read` trả timeout 500 ms nhưng statement có `setTimeout(Duration.ofSeconds(1))`, hàm `logProfile(pointRead)` vẫn in **500 ms**, vì profile object không biết một request cụ thể đã override gì.

Để xác định effective timeout của một statement:

1. Biết statement chọn **profile nào** (mặc định/named/derived).
2. Đọc thuộc tính tường minh của statement, ví dụ `getTimeout()`; giá trị `null` nghĩa là kế thừa trong API Request.
3. Nếu không có override, đọc `profile.getDuration(REQUEST_TIMEOUT)`.
4. Nếu có override, dùng **giá trị statement**.

Pseudocode:

~~~text
effective_timeout(request):
    if request.getTimeout() != null:
        return request.getTimeout()
    else:
        return selected_profile.getDuration(REQUEST_TIMEOUT)
~~~

Đây là quy tắc tư duy cho **request timeout**, không thay thế đầy đủ internals của driver về retry, timer tick, first-page/next-page, custom policies hoặc lỗi connect. Đối với CL/page/idempotence, cần áp dụng quy tắc inheritance riêng và semantics của tùy chọn đó.

### 8.3. Truy xuất config không chỉ để in debug

Có thể dùng typed getters để:

- Kiểm **SLO policy** khi startup: `point_read` không được có timeout vượt ngưỡng đã duyệt.
- Kiểm CL không bị vô ý hạ xuống `ONE` sau một deploy.
- So sánh config **trước và sau reload** ở canary.
- Ghi dấu version/hash của nguồn config mà không lộ password.
- Triển khai self-diagnostic endpoint **chỉ lộ allowlisted non-secret settings** cho operator.

Không serialize toàn bộ `DriverConfig`, contact points, credentials hoặc truststore passwords ra log/debug endpoint công khai. Các values đã resolve vẫn có thể chứa secrets.

## 9. `DriverConfigLoader`: nạp bằng file, classpath hoặc bằng Java

### 9.1. Mặc định: tìm `application.conf` trên classpath

~~~java
import com.datastax.oss.driver.api.core.CqlSession;

// Khi application.conf chứa contact-points và local-datacenter
// phù hợp, loader mặc định đọc cấu hình từ classpath.
try (CqlSession session = CqlSession.builder().build()) {
    DriverEffectiveConfig.print(session);
}
~~~

Với dự án Maven, đặt `application.conf` tại `src/main/resources/`; sau build, phải chắc nó nằm trong runtime classpath/JAR thực tế. Với Spring Boot hoặc framework có cấu hình Cassandra riêng, cần phân biệt `spring.cassandra.*` hay config framework với `datastax-java-driver.*`: không mặc định một hệ thống tự đồng bộ sang hệ thống kia.

### 9.2. Chọn file ngoài classpath

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.io.File;

File configFile = new File("/etc/order-api/cassandra-driver.conf");

try (CqlSession session = CqlSession.builder()
        .withConfigLoader(DriverConfigLoader.fromFile(configFile))
        .build()) {
    DriverEffectiveConfig.print(session);
}
~~~

Với `fromFile`, nguồn ưu tiên là **system properties → file chỉ định → reference.conf**. Đây là cơ chế hữu ích khi cấu hình được mount dưới dạng file bên ngoài ứng dụng; tuy nhiên cần bảo đảm quyền đọc, atomic replacement khi cập nhật và ghi nhận file version/checksum. Không tự kỳ vọng loader còn lấy thêm `application.conf` trong JAR nếu đã chọn `fromFile`.

### 9.3. Một số factory khác

| API | Ý nghĩa | Lưu ý |
|---|---|---|
| `DriverConfigLoader.fromClasspath("mydriver")` | Đọc `mydriver.conf`/`mydriver.json`/`mydriver.properties` trên classpath | Không nhầm prefix resource với root `datastax-java-driver` |
| `DriverConfigLoader.fromFile(file)` | Đọc một file ngoài classpath | File phải tồn tại/đọc được ở máy chạy JVM |
| `DriverConfigLoader.fromPath(path)` | Tương tự với `java.nio.file.Path` | Xác minh reloader theo binary |
| `DriverConfigLoader.fromUrl(url)` | Đọc từ URL | Quản lý trust/network/failure cache riêng |
| `DriverConfigLoader.fromString(contents)` | Đọc HOCON string | **Không hỗ trợ runtime reload** theo API 4.17 |
| `DriverConfigLoader.programmaticBuilder()` | Overrides bằng Java có fallback từ config | System properties vẫn có thể thắng |
| `DriverConfigLoader.fromMap(options)` | Cấu hình từ in-memory options map | Xem version/API để biết reload semantics |

Không truyền URL chứa credentials hoặc serialize nguyên config HOCON có secret ra logs. File resource `reference.conf` trong driver JAR **không nên sửa** để đổi defaults; giữ overrides của ứng dụng trong một nguồn quản lý được.

### 9.4. Programmatic config loader với named profiles

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.net.InetSocketAddress;
import java.time.Duration;

DriverConfigLoader loader = DriverConfigLoader.programmaticBuilder()
    .withDuration(
        DefaultDriverOption.REQUEST_TIMEOUT,
        Duration.ofSeconds(2))
    .withString(
        DefaultDriverOption.REQUEST_CONSISTENCY,
        "LOCAL_ONE")
    .withInt(
        DefaultDriverOption.REQUEST_PAGE_SIZE,
        500)
    .startProfile("point_read")
        .withDuration(
            DefaultDriverOption.REQUEST_TIMEOUT,
            Duration.ofMillis(500))
        .withInt(
            DefaultDriverOption.REQUEST_PAGE_SIZE,
            25)
        .withBoolean(
            DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE,
            true)
    .endProfile()
    .startProfile("history_read")
        .withDuration(
            DefaultDriverOption.REQUEST_TIMEOUT,
            Duration.ofSeconds(5))
        .withInt(
            DefaultDriverOption.REQUEST_PAGE_SIZE,
            100)
        .withBoolean(
            DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE,
            true)
    .endProfile()
    .build();

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("datacenter1")
        .withConfigLoader(loader)
        .build()) {
    DriverEffectiveConfig.print(session);
}
~~~

**Giải thích:**

- `withDuration`/`withInt`/`withString`/`withBoolean` là **typed options**, không ép tùy ý tất cả thành String.
- `startProfile` đặt các options tiếp theo vào **named profile**; `endProfile` trả về default scope.
- `withLocalDatacenter` và `addContactPoint` áp dụng vào session builder, phù hợp khi địa chỉ đến từ service discovery hoặc cấu hình deployment.
- Đây là **cách khai báo thay thế** cho HOCON, không nên dùng **đồng thời** hai bản khác nhau mà không biết thứ tự ưu tiên: programmatic overrides đứng trên application.conf nhưng dưới system properties.
- Các giá trị `LOCAL_ONE`/DC lab và 500 ms chỉ để học; production có thể cần `LOCAL_QUORUM` với RF phù hợp.

### 9.5. Kiểm tra xung đột giữa file và programmatic

Nếu `application.conf` khai báo `point_read` timeout 800 ms, code programmatic khai báo `point_read` 500 ms thì effective profile sẽ có 500 ms, **trừ khi system property còn ưu tiên cao hơn cho đúng option/path**. Nếu bạn chỉ đọc file rồi giải thích 800 ms, bạn đang đánh giá **declared config** chứ không phải runtime resolved config.

## 10. Hot reload: chỉnh file không có nghĩa mọi tùy chọn đổi ngay

### 10.1. Reload hoạt động thế nào?

Default Typesafe Config loader của Java Driver 4.17 hỗ trợ reload theo chu kỳ:

~~~hocon
datastax-java-driver {
  basic.config-reload-interval = 5 minutes
}
~~~

Đặt interval `0` để tắt periodic reload. Khi file có thay đổi và loader reload thành công, driver cập nhật **những options được đánh dấu runtime-modifiable**. Một số thay đổi như protocol version, một số policy hoặc cấu trúc connection không thể áp dụng nóng chỉ nhờ thay HOCON; có trường hợp yêu cầu tạo session mới/redeploy.

~~~text
T0: session khởi tạo, config C0
    |
    v
T1: operator thay file config từ C0 -> C1
    |
    +-- File nằm trong JAR read-only?
    |       -> Không có thay đổi thật trong runtime resource
    |
    +-- File external và loader hỗ trợ reload?
            |
            v
       Chu kỳ reload / manual reload
            |
     +------+------+
     |             |
   MODIFIABLE   NON-MODIFIABLE
     |             |
 New requests    Thường cần
 dùng C1         session rebuild/redeploy
~~~

### 10.2. Manual reload từ Java

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.util.concurrent.CompletionStage;

public final class ConfigReloader {
    private ConfigReloader() {}

    public static CompletionStage<Boolean> reload(CqlSession session) {
        DriverConfigLoader loader =
            session.getContext().getConfigLoader();

        if (!loader.supportsReloading()) {
            throw new IllegalStateException(
                "Configured loader does not support manual reload");
        }

        // Boolean = configuration actually changed on reload,
        // not "every configured component has been reinitialized".
        return loader.reload();
    }
}
~~~

Sử dụng trong một luồng vận hành riêng:

~~~java
ConfigReloader.reload(session).whenComplete((changed, error) -> {
    if (error != null) {
        System.err.println("Config reload failed: " + error);
    } else {
        System.out.println("Driver config changed=" + changed);
        DriverEffectiveConfig.print(session);
    }
});
~~~

`supportsReloading()` phải được kiểm vì custom loader và `fromString` có thể không hỗ trợ. `reload()` trả `CompletionStage<Boolean>`; `true` báo cấu hình **đã thay đổi**, **không** bảo đảm mọi resource, connection và policy đã tái tạo. Để kết luận một option có hiệu lực cần **đọc lại typed getter + xem tài liệu option và đo request mới**.

### 10.3. Đổi một option có thể reload được

Theo reference.conf 4.17:

| Option | Runtime-modifiable? | Được phép override trong profile? | Cách kiểm |
|---|---|---|---|
| `basic.request.timeout` | Có, với **request mới** | Có | `REQUEST_TIMEOUT` |
| `basic.request.consistency` | Có | Có | `REQUEST_CONSISTENCY` |
| `basic.request.serial-consistency` | Có | Có | `REQUEST_SERIAL_CONSISTENCY` |
| `basic.request.page-size` | Có | Có | `REQUEST_PAGE_SIZE` |
| `basic.request.default-idempotence` | Có | Có | `REQUEST_DEFAULT_IDEMPOTENCE` |
| `basic.config-reload-interval` | Chế độ reload theo loader | **Không** | Đọc loader/config option và thử reload |
| `basic.load-balancing-policy.class` | **Không** reload class mặc định | Có thể config theo profile, tùy policy | Thường cần session rebuild |
| `advanced.netty.timer.tick-duration` | **Không** | **Không** | Chọn lúc init JVM/session |

Không suy từ tên `advanced.*` rằng mọi option đều không thể thay nóng hoặc từ `basic.*` rằng mọi option đều có thể reload. **Reference configuration ghi rõ từng option** với hai thuộc tính riêng: modifiable at runtime và overridable in profile.

### 10.4. Named profiles và reload

Nếu `history_read` có timeout 5 s và operator đổi thành 6 s trong file ngoài JAR, các request **mới** sử dụng named profile này sẽ thấy giá trị 6 s **sau khi reload thành công**, miễn không có system/statement override và option có hỗ trợ runtime modification.

Nhưng:

- Những request **đã gửi trước reload** không được đảm bảo chuyển deadline giữa chừng.
- Statements có `setTimeout(1s)` **vẫn 1 s**.
- Nếu system property cho `datastax-java-driver.profiles.history_read.basic.request.timeout` là 4 s, file đổi 5→6 s vẫn **bị property 4 s che**.
- Application config được đóng gói trong JAR read-only **không tự thay** khi bạn sửa source code; cần deploy resource mới.
- Derived profiles từ base có thể phản ánh reload theo cơ chế reference, nhưng nên cache và thử trên phiên bản thực.

### 10.5. Điều kiện rollback sau reload

Một change record cần ghi:

~~~text
Change ID: DRIVER-PROFILE-ROLL-001
Scope: order-api / dc1 / 1 canary instance
Profile: history_read
Option: basic.request.timeout
Effective before: 5 seconds
Proposed: 6 seconds
Trigger: timeout rate, p99, pool in-flight, retry amplification
Rollback: restore external config value 5 seconds
Verify: reload success + typed getter + new-request metrics
~~~

Nếu tăng timeout chỉ làm client chờ lâu hơn nhưng server tiếp tục quá tải, không coi đó là “sửa latency”. Rollback phải theo dõi **user-visible error budget**, physical attempts và resource của Cassandra, không chỉ kiểm effective value đã về C0.

## 11. Năm request options cần hiểu trước khi đưa profile vào production

### 11.1. `basic.request.consistency`: yêu cầu về replica, không phải performance switch

Mỗi CQL read/write có consistency level (CL), ảnh hưởng điều kiện phản hồi của coordinator. Ví dụ với `NetworkTopologyStrategy` ở `dc1` có RF=3:

| CL | Điều kiện phản hồi khái quát | Đánh đổi |
|---|---|---|
| `ONE` | Một replica đáp ứng | Latency/availability có thể tốt hơn; yêu cầu nhất quán thấp hơn |
| `LOCAL_ONE` | Một replica trong local DC | Tránh buộc remote DC cho request local |
| `LOCAL_QUORUM` | Quorum của full replicas ở **local DC** (RF=3 thường cần 2) | Có thể tăng latency so với ONE nhưng đảm bảo theo quorum |
| `QUORUM` | Quorum theo tập replica áp dụng của keyspace | Có thể liên quan nhiều DC tùy RF/topology |
| `ALL` | Cần phản hồi từ tất cả full replicas theo semantics CL | Khó đạt availability khi replica không khỏe |

`LOCAL_QUORUM` với RF=3 cần **hai** phản hồi trong local DC cho thao tác thông thường. Một profile `fast_read` đặt `ONE` không được dùng chỉ để giảm p99 nếu hợp đồng nghiệp vụ đòi `LOCAL_QUORUM`. CL cũng không thay thế repair hoặc kiểm replica consistency.

Ví dụ config:

~~~hocon
datastax-java-driver {
  basic.request.consistency = LOCAL_QUORUM
  profiles {
    payments {
      basic.request.consistency = LOCAL_QUORUM
    }
  }
}
~~~

**Đừng nhầm CL với replication factor.** RF được định nghĩa trên keyspace, CL là yêu cầu trên **request**. Đổi file Java Driver **không** tạo thêm bản sao dữ liệu; thay RF sau khi đã có dữ liệu có thể đòi repair/rebuild/streaming trong runbook Cassandra.

### 11.2. `basic.request.serial-consistency`: cho LWT/Paxos

Serial consistency level áp dụng vào các conditional mutations kiểu `IF ...` (LWT). Những giá trị như `SERIAL` hoặc `LOCAL_SERIAL` kiểm soát phần Paxos/serial semantics; nó **khác với** normal CL cho phase mutation.

~~~sql
-- CQL LAB cho thấy một conditional write.
INSERT INTO driver_lab.orders_by_id (
    tenant_id, order_id, status
) VALUES (
    'tenant-a',
    11111111-1111-1111-1111-111111111111,
    'NEW'
) IF NOT EXISTS;
~~~

Nếu ứng dụng không dùng LWT, đổi serial consistency trong profile **không làm point SELECT nhanh hơn**. Với LWT phải đặt **normal CL và serial CL cùng lúc** theo phạm vi DC/consistency mong muốn; không dùng `LOCAL_SERIAL` như cách “giảm một nửa chi phí” mặc định. Chú ý những trường hợp driver/framework có thể ghi đè hai option này trên statement.

### 11.3. `basic.request.timeout`: một deadline client, không phải rollback của server

Java Driver 4.x coi `REQUEST_TIMEOUT` là **ngân sách cho một request**, bao gồm những retry/speculative attempts trong request đó. Một lần `session.execute(stmt)` bị timeout không chứng minh Cassandra chưa xử lý mutation; replica có thể đã ghi thành công nhưng ACK không về client.

~~~text
Client                    Coordinator / replicas
   |                               |
   |--- CQL mutation -------------->|
   |                               | ghi commit log/memtable
   |              (ACK chậm/mất)   |
   |-- timeout sau 2 giây ---------X
   |
Client không biết chắc write đã áp dụng hay chưa.
Retry phải theo idempotency và nguồn sự thật.
~~~

Ví dụ:

~~~java
SimpleStatement request = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setExecutionProfileName("point_read")
    .setTimeout(Duration.ofMillis(800))
    .build();
~~~

Timeout 800 ms là **override** so với 500 ms của profile. Không đặt timeout 20 ms rồi cho rằng mọi request sẽ timeout đúng từng mili-giây: driver dùng timer resolution/tick và cần tính network, GC, queue; reference config cũng cảnh báo timeout phải phù hợp `advanced.netty.timer.tick-duration`.

**Paging nuance:** Nếu code duyệt một `ResultSet` có nhiều trang, mỗi lần fetch trang có thể là một request tiếp theo với ngân sách riêng. `REQUEST_TIMEOUT` của request đầu không tự trở thành deadline tuyệt đối cho **toàn bộ API workflow** đọc hết 100 trang. API cần thêm **end-to-end deadline**, max rows/pages và cancellation/backpressure.

### 11.4. `basic.request.page-size`: cỡ trang, không phải LIMIT

~~~java
SimpleStatement pageRequest = SimpleStatement.builder(
        "SELECT event_time, event_id, status " +
        "FROM driver_lab.events_by_tenant_day " +
        "WHERE tenant_id = ? AND day = ?")
    .addPositionalValues("tenant-a",
                         java.time.LocalDate.parse("2026-11-21"))
    .setExecutionProfileName("history_read")
    .setPageSize(20)
    .build();
~~~

`setPageSize(20)` có nghĩa driver yêu cầu **khoảng 20 rows cho một trang**, không giới hạn tổng kết quả ở 20. Khi iterate `ResultSet`, driver có thể tự fetch thêm trang. Với async API, ứng dụng quản lý fetch-next-page; tránh đọc toàn bộ dataset vào bộ nhớ client. Page size quá lớn làm payload/network/client heap tăng; quá nhỏ tạo nhiều round trips.

So sánh:

~~~sql
-- LIMIT giới hạn tổng số row của truy vấn theo semantics CQL.
SELECT event_time, event_id, status
FROM driver_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
LIMIT 50;
~~~

`LIMIT 50` khác `page-size=20`: một truy vấn LIMIT 50 có thể được trả qua nhiều trang nhỏ. Truy vấn có partition rộng/tombstones nhiều vẫn có thể đọc nhiều cells để tìm 50 rows. **Không dùng page size thay thiết kế partition key hoặc giới hạn API.**

Giá trị 0/âm có thể được driver xử lý như bỏ paging theo reference của một số options; đừng dựa vào nó để tải bảng lớn vì có thể bùng memory hoặc response.

### 11.5. `basic.request.default-idempotence`: điều kiện cho retry/speculation

Một request idempotent khi **lặp lại cùng tác động không đổi trạng thái cuối** theo semantics của thao tác và nghiệp vụ. Driver cần thông tin này để quyết định có thể an toàn thử lại hoặc speculative execution trong những tình huống nhất định.

| Request | Có thể idempotent? | Cần kiểm |
|---|---|---|
| SELECT điểm | Thường có | Không có side effect ngoại vi |
| INSERT upsert cùng PK và values | Có điều kiện | Timestamp/TTL/nguồn dữ liệu và concurrency |
| UPDATE cùng giá trị literal | Có điều kiện | Timestamp, write conflict, TTL |
| UPDATE counter `counter = counter + 1` | **Không** | Lặp làm tăng nhiều lần |
| Conditional write `IF NOT EXISTS` | Không mặc định coi retry vô hại | `[applied]`, contention, business outcome |
| Ghi UUID mới mỗi lần thử | **Không** | Retry tạo rows mới |
| DELETE một row | Có điều kiện | Tombstone timestamp, retention, event order |

Mặc định trong reference config 4.17 là `default-idempotence=false`. Đặt `true` trong **profile dành riêng cho SELECT** có thể hợp lý. Không đặt `basic.request.default-idempotence=true` trên toàn service mixed read/write chỉ để speculative retry được bật nhiều hơn.

~~~java
// Statement-level quyết định chủ động sau khi xác minh nghiệp vụ.
SimpleStatement s = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setIdempotent(true)
    .build();
~~~

**Driver flag không biến thao tác không idempotent thành idempotent**. Nếu retry sau timeout và client tự sinh timestamp/UUID mới, tính đúng phải được thiết kế tại application, không dựa vào một boolean trong config.

### 11.6. Request profile và cluster health

Một profile có `LOCAL_QUORUM`, timeout 3 s và page-size 100 **không bảo đảm** truy vấn chậm biến mất:

- Node bị disk/GC overload, coordinator không đủ replica đúng lúc.
- Partition key tạo hotspot, range scans chạm nhiều SSTables/tombstones.
- Data centers có replication chưa đủ hoặc một replica ở trạng thái DOWN.
- Java Driver pool quá nhiều in-flight requests hoặc retry tạo thêm tải.
- Một query phải fetch nhiều pages làm API end-to-end latency lớn.

Hãy ghép **config introspection** với JMX `ClientRequest`/`Table`, `nodetool status`/`tpstats`, Java driver metrics và phân tích query family.

## 12. Thiết kế execution profiles theo SLO và loại workload

### 12.1. Tách OLTP, history và DDL

Một ứng dụng đặt hàng thường có:

~~~text
REST GET /orders/{id}
   -> point_read
   -> lookup theo partition key
   -> response nhỏ, p99 SLO nghiêm ngặt

REST GET /orders/history
   -> history_read
   -> đọc nhiều rows theo clustering range và paging
   -> giới hạn page/results, timeout dài hơn

Migration / CREATE TABLE
   -> ddl
   -> tần suất hiếm, timeout dài hơn cho schema agreement
~~~

Vì sao dùng profiles tốt hơn `if/else` khắp code:

- Một nơi nêu rõ timeout/CL/page/idempotence theo loại request.
- Dễ đọc effective options và so trước–sau deploy.
- Tránh một method sửa request timeout vì vô tình “mượn” policy của loại khác.
- Hỗ trợ canary một profile mà không thay mọi query.
- Có thể kiểm bằng unit/integration tests rằng repository dùng đúng tên.

### 12.2. Ma trận policy minh họa

| Profile | Timeout giả định | CL giả định | Page size | Idempotence mặc định | Chính sách |
|---|---:|---|---:|---|---|
| `point_read` | 500 ms | LOCAL_QUORUM | 25 | true | Chỉ point SELECT đã kiểm |
| `history_read` | 5 s | LOCAL_QUORUM | 100 | true | Đọc theo partition/range có paging |
| `write_critical` | 3 s | LOCAL_QUORUM | 500 | false | Mutation cần idempotency explicit |
| `ddl` | 15 s | LOCAL_QUORUM | 500 | false | Thao tác schema riêng, không trộn API |

Những số này **không phải mặc định** của driver hay thông số khuyến nghị cho mọi cluster. Với RF3 ở một DC, `LOCAL_QUORUM` thường cần 2 replica phản hồi. Trong lab RF1, cấu hình có thể dùng `LOCAL_ONE`/`ONE` để học; đừng chuyển CL giữa các pha benchmark rồi kết luận profile mới “nhanh hơn”.

### 12.3. Profile không đủ nếu request cần nhiều pages

Ví dụ trang lịch sử trả mỗi page 100 rows, người dùng thực sự yêu cầu xem 10.000 rows:

~~~text
history_read.page-size = 100
Số page cần fetch ≈ 100 (bỏ qua điều kiện dataset/filter)
Mỗi page có latency riêng.
Tổng thời gian API có thể vượt 5 giây dù từng page <5 giây.
~~~

Giải pháp đúng có thể là **cursor/paging API**, giới hạn maximum rows/pages, query time bucket, cache hợp lý hoặc thiết kế lại data model. **Không** chỉ tăng `history_read.timeout` lên 60 giây để che việc đọc quá nhiều.

### 12.4. Không dùng một profile cho nhiều semantics không tương thích

Một profile `fast` dùng cả SELECT, INSERT, LWT và bulk export dễ bị tối ưu sai: timeout thấp làm schema mutation lỗi, idempotence=true sai với counter, CL không phù hợp nghiệp vụ và page size quá lớn cho export. Nên nhóm theo **policy thực sự chung**, không chỉ dựa vào tên REST endpoint hoặc team sở hữu.

## 13. Lab CQL — tạo workload để thử profiles

**Mục tiêu lab:** Hai query families trên một bảng có partition key composite, sau đó Java sẽ gọi chúng bằng `point_read` và `history_read`. Lab chỉ đo **hành vi chọn cấu hình**, không phải benchmark Cassandra hoặc so sánh hiệu năng giữa CL.

**Môi trường:** Một Cassandra node 4.1/5.0 đang chạy; `cqlsh`, Java 17, Java Driver 4.x tương thích, quyền tạo keyspace/table. `SimpleStrategy` và RF1 chỉ dùng cho lab; production nhiều DC cần `NetworkTopologyStrategy` và RF phù hợp.

### Bước 1 — Kiểm tên DC thật

~~~bash
# Quan sát, không thay dữ liệu:
nodetool status
nodetool describecluster
~~~

Nếu `nodetool status` cho biết DC là `dc1` thay vì `datacenter1`, sửa `application.conf` hoặc `withLocalDatacenter` cho khớp. **Không đổi tên DC trong giả định** rồi cho rằng driver sẽ tự suy đúng.

### Bước 2 — Tạo keyspace/bảng

~~~sql
CREATE KEYSPACE IF NOT EXISTS driver_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS driver_lab.events_by_tenant_day (
    tenant_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    status text,
    payload text,
    PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS driver_lab.orders_by_id (
    tenant_id text,
    order_id uuid,
    status text,
    PRIMARY KEY ((tenant_id), order_id)
);
~~~

Giải thích:

- `events_by_tenant_day` có partition key `(tenant_id,day)` và clustering key `(event_time,event_id)`, phù hợp lịch sử theo ngày.
- `orders_by_id` dùng key `(tenant_id),order_id`; trong production một tenant rất lớn có thể cần xem lại partition model.
- `status` là regular column, không tự cho phép scan toàn cluster hiệu quả.
- Execution profile **không thể sửa một CQL thiếu partition key** thành truy vấn tốt; data model vẫn là bước riêng.

### Bước 3 — Nhập dữ liệu cố định

~~~sql
CONSISTENCY ONE;

INSERT INTO driver_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
  11111111-1111-1111-1111-111111111111,
  'NEW', 'created'
);

INSERT INTO driver_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:05:00Z',
  22222222-2222-2222-2222-222222222222,
  'PAID', 'payment accepted'
);

INSERT INTO driver_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:10:00Z',
  33333333-3333-3333-3333-333333333333,
  'SHIPPED', 'out for delivery'
);

INSERT INTO driver_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES (
  'tenant-b', '2026-11-21', '2026-11-21T09:00:00Z',
  44444444-4444-4444-4444-444444444444,
  'NEW', 'created'
);

INSERT INTO driver_lab.orders_by_id
  (tenant_id, order_id, status)
VALUES (
  'tenant-a', 11111111-1111-1111-1111-111111111111, 'NEW'
);
~~~

Lab dùng `CONSISTENCY ONE` phù hợp RF1. Với production RF3, đừng áp dụng mức ONE chỉ vì lệnh lab chạy nhanh.

### Bước 4 — Xác minh truy vấn theo partition key

~~~sql
SELECT event_time, event_id, status
FROM driver_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

SELECT event_time, event_id, status
FROM driver_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND event_time = '2026-11-21T08:05:00Z'
  AND event_id = 22222222-2222-2222-2222-222222222222;
~~~

Kỳ vọng truy vấn đầu trả ba rows (thường theo `event_time DESC`), truy vấn thứ hai trả đúng `PAID`. Với vài rows, thay `page-size=25` và `page-size=100` **không tạo khác biệt performance rõ**, vì tập kết quả quá nhỏ; mục đích là kiểm profile selection/effective values.

## 14. Lab Java — in profile, thực thi CQL và thử statement override

### 14.1. Cấu trúc ứng dụng

~~~text
driver-profile-lab/
  src/main/java/example/DriverProfileLab.java
  src/main/resources/application.conf
  pom.xml hoặc build.gradle (do dự án tự cấu hình)
~~~

Dependency cần có Java Driver core 4.x tương thích với Cassandra đang chạy và logger binding phù hợp. Bài chỉ tạo **nội dung code**, không tự tạo file dự án hoặc chạy Maven/Gradle. Đối với Java Driver 4.18+ (ASF), Maven coordinates có thể khác so với 4.17; kiểm tài liệu của version đang chọn trước khi build.

Nội dung `application.conf` dùng **mẫu lab ở mục 6.1**. Nếu một app framework đã cấu hình Cassandra qua bean/config riêng, dùng duy nhất cơ chế tích hợp được kiểm để không có hai `CqlSession` trỏ khác DC.

### 14.2. Ứng dụng hoàn chỉnh

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfig;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class DriverProfileLab {
    private DriverProfileLab() {}

    public static void main(String[] args) {
        // app.conf chứa contact-points và local-datacenter thật.
        try (CqlSession session = CqlSession.builder().build()) {
            DriverConfig config = session.getContext().getConfig();
            DriverExecutionProfile defaults =
                config.getDefaultProfile();
            DriverExecutionProfile point =
                config.getProfile("point_read");
            DriverExecutionProfile history =
                config.getProfile("history_read");

            print("default", defaults);
            print("point_read", point);
            print("history_read", history);

            // Point lookup: tường minh profile point_read.
            PreparedStatement getOne = session.prepare(
                "SELECT event_time, event_id, status " +
                "FROM driver_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND day = ? " +
                "AND event_time = ? AND event_id = ?");

            BoundStatement one = getOne.bind(
                "tenant-a",
                LocalDate.parse("2026-11-21"),
                Instant.parse("2026-11-21T08:05:00Z"),
                UUID.fromString(
                    "22222222-2222-2222-2222-222222222222"))
                .setExecutionProfileName("point_read");

            Row row = session.execute(one).one();
            System.out.println("point status=" +
                (row == null ? "(missing)" : row.getString("status")));

            // Đọc theo partition và paging: profile history_read.
            PreparedStatement list = session.prepare(
                "SELECT event_time, event_id, status " +
                "FROM driver_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND day = ?");

            BoundStatement listStatement = list.bind(
                "tenant-a", LocalDate.parse("2026-11-21"))
                .setExecutionProfileName("history_read");

            ResultSet result = session.execute(listStatement);
            int rows = 0;
            for (Row next : result) {
                rows++;
                System.out.println("history=" +
                    next.getInstant("event_time") + " " +
                    next.getString("status"));
            }
            System.out.println("history rows=" + rows);

            // Một request dùng history profile, nhưng riêng timeout
            // và page-size bị override tường minh.
            SimpleStatement overridden = SimpleStatement.builder(
                    "SELECT event_time, status " +
                    "FROM driver_lab.events_by_tenant_day " +
                    "WHERE tenant_id = ? AND day = ?")
                .addPositionalValues(
                    "tenant-a", LocalDate.parse("2026-11-21"))
                .setExecutionProfileName("history_read")
                .setTimeout(Duration.ofSeconds(1))
                .setPageSize(2)
                .build();

            System.out.println("explicit timeout=" +
                overridden.getTimeout());
            System.out.println("explicit pageSize=" +
                overridden.getPageSize());

            int overriddenRows = 0;
            for (Row next : session.execute(overridden)) {
                overriddenRows++;
            }
            System.out.println("override rows=" + overriddenRows);
        }
    }

    private static void print(
            String label, DriverExecutionProfile profile) {
        System.out.printf(
            "%s: name=%s timeout=%s consistency=%s " +
            "pageSize=%d idempotentDefault=%s%n",
            label,
            profile.getName(),
            profile.getDuration(DefaultDriverOption.REQUEST_TIMEOUT),
            profile.getString(DefaultDriverOption.REQUEST_CONSISTENCY),
            profile.getInt(DefaultDriverOption.REQUEST_PAGE_SIZE),
            profile.getBoolean(
                DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE));
    }
}
~~~

**Các điểm cần quan sát:**

1. `session.getContext().getConfig()` trả những **profiles đã merge** từ HOCON.
2. `getProfile("point_read")` và `getProfile("history_read")` cho named profiles có kiểu dữ liệu đúng.
3. `getOne.bind(...).setExecutionProfileName(...)` chọn named profile, không tạo session mới.
4. `SimpleStatement.Builder` đặt timeout=1s/page-size=2; hai giá trị tường minh này thắng `history_read`.
5. `getTimeout()`/`getPageSize()` đọc **thuộc tính statement**, không phải “thời gian thực mất bao lâu”.
6. `for (Row ... : result)` có thể tự fetch pages tiếp theo. Với 3 rows và page-size 2, code còn đọc đủ ba rows, không dừng ở hai.

### 14.3. Output dự kiến (minh họa, không đo latency)

~~~text
default: name=default timeout=PT2S consistency=LOCAL_ONE pageSize=500 idempotentDefault=false
point_read: name=point_read timeout=PT0.5S consistency=LOCAL_ONE pageSize=25 idempotentDefault=true
history_read: name=history_read timeout=PT5S consistency=LOCAL_ONE pageSize=100 idempotentDefault=true
point status=PAID
history=2026-11-21T08:10:00Z SHIPPED
history=2026-11-21T08:05:00Z PAID
history=2026-11-21T08:00:00Z NEW
history rows=3
explicit timeout=PT1S
explicit pageSize=2
override rows=3
~~~

**Không hard-code expected values nếu môi trường có system properties.** Nếu command line đặt `-Ddatastax-java-driver.profiles.point_read.basic.request.timeout=...`, output sẽ khác mẫu. Phải **giải thích chênh lệch theo precedence**, không tự sửa HOCON hoặc tắt property mà chưa biết ai quản lý.

### 14.4. Ghi lại bảng quan sát

| Request | Profile được chọn | Timeout từ profile | Timeout statement | Timeout kỳ vọng |
|---|---|---|---|---|
| `getOne` | point_read | 500 ms | null | 500 ms |
| `listStatement` | history_read | 5 s | null | 5 s |
| `overridden` | history_read | 5 s | 1 s | **1 s** |
| `SimpleStatement` không profile/timeout | default | 2 s | null | 2 s |

Lập bảng tương tự cho page size và CL. Đây là cách chứng minh effective-value logic trước khi bước sang thử **hot reload**.

## 15. Bài lab ưu tiên nguồn: xác minh một system property

Mục tiêu: kiểm nguồn cao nhất trong cơ chế loader mà **không sửa file YAML/Cassandra**.

### Bước 1 — Ghi baseline

Chạy chương trình lab với `application.conf` của mục 6, ghi timeout của default/point/history và đảm bảo query CQL chạy đúng.

### Bước 2 — Chạy JVM với property override

~~~bash
# Ví dụ trên JVM lab, shell Unix/Linux.
# Tham số -D phải đứng trước -jar.
java -Ddatastax-java-driver.basic.request.timeout="4 seconds" \
     -jar driver-profile-lab.jar
~~~

**Điều phải xảy ra** nếu property thật sự đến được JVM và không có programmatic/custom loader khác che:

- Default timeout từ 2 s → **4 s**.
- `point_read` vẫn **500 ms** vì profile override timeout riêng.
- `history_read` vẫn **5 s** vì profile override timeout riêng.
- Statement `overridden` vẫn **1 s**.

Không lấy ví dụ này làm benchmark latency. Nó chứng minh **thứ tự nguồn cấu hình và mức độ override**, không chứng minh deadline nào là tốt hơn.

### Bước 3 — Override một named profile cụ thể

~~~bash
java -Ddatastax-java-driver.profiles.history_read.basic.request.timeout="7 seconds" \
     -jar driver-profile-lab.jar
~~~

Kỳ vọng `history_read` effective timeout là **7 giây**, vì system property nhắm đúng đường dẫn profile. Nếu JVM chỉ override `basic.request.timeout` ở default, timeout 5 s trong `history_read` vẫn thắng default inherited value.

### Bước 4 — Kết quả không như dự đoán?

Kiểm tuần tự:

1. Property có đúng **prefix và case/path** không?
2. Có truyền `-D` tới **đúng JVM process** không?
3. Application dùng loader mặc định, `fromFile`, programmatic hay custom?
4. Profile `history_read` có thực sự tồn tại và được statement chọn không?
5. Có explicit `setTimeout` trên statement không?
6. Có file cấu hình của framework khác được merge không?
7. Java logging endpoint in giá trị từ config object hay từ một file cũ được cache?

**Khôi phục sau lab:** Bỏ `-D` trong command line/entrypoint, khởi động lại JVM theo cấu hình cũ, và đọc lại effective values. Đừng để system property thử nghiệm tồn tại trong deployment production.

## 16. Lab hot reload bằng file ngoài JAR

**Mục tiêu:** Chứng minh một option runtime-modifiable cập nhật vào profile sau reload, trong khi statement có explicit override vẫn giữ giá trị riêng. Lab này cần app đang chạy liên tục hoặc một test harness có khả năng giữ `CqlSession`, chứ không chỉ gọi `main` rồi process thoát ngay.

### 16.1. Chuẩn bị file cấu hình có thể thay đổi

~~~text
/etc/driver-lab/driver.conf
  datastax-java-driver {
    basic.contact-points = [ "127.0.0.1:9042" ]
    basic.load-balancing-policy.local-datacenter = "datacenter1"
    basic.config-reload-interval = 0
    basic.request.timeout = 2 seconds
    basic.request.consistency = LOCAL_ONE
    profiles {
      history_read {
        basic.request.timeout = 5 seconds
        basic.request.page-size = 100
      }
    }
  }
~~~

`0` tắt **periodic reload** để bài thử điều khiển **manual reload** một cách xác định. HOCON trong khối trên là nội dung file lab, không phải output của driver. Phải thay `datacenter1` theo DC thực; tránh tạo/đổi file trong production chỉ để thử.

### 16.2. Khởi tạo session từ file

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.io.File;

DriverConfigLoader loader = DriverConfigLoader.fromFile(
    new File("/etc/driver-lab/driver.conf"));

CqlSession session = CqlSession.builder()
    .withConfigLoader(loader)
    .build();

// Giữ session mở trong suốt thí nghiệm;
// cuối cùng gọi session.close() hoặc try-with-resources.
~~~

### 16.3. Thay file rồi kích hoạt reload

Sau khi tạo session, trên host lab sửa **chỉ một dòng**:

~~~diff
- basic.request.timeout = 5 seconds
+ basic.request.timeout = 6 seconds
~~~

Chú ý đây là dòng **bên trong `profiles.history_read`**, không phải default `basic.request.timeout`. Lưu file atomic nếu có automation. Sau đó gọi:

~~~java
DriverConfigLoader activeLoader =
    session.getContext().getConfigLoader();

if (activeLoader.supportsReloading()) {
    boolean changed =
        activeLoader.reload().toCompletableFuture().join();

    System.out.println("reload changed=" + changed);
    System.out.println(
        session.getContext().getConfig()
            .getProfile("history_read")
            .getDuration(DefaultDriverOption.REQUEST_TIMEOUT));
}
~~~

Kỳ vọng sau reload: timeout `history_read` từ `PT5S` thành `PT6S`. Nếu `changed=false`, kiểm file path, quyền, precedence của system properties và việc file có thực sự đổi. Nếu reload ném exception, **giữ trạng thái trước được xác nhận**, sửa config và thử lại có kiểm soát; không tiếp tục rollout.

### 16.4. Statement-level override vẫn thắng

~~~java
SimpleStatement s = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setExecutionProfileName("history_read")
    .setTimeout(Duration.ofSeconds(1))
    .build();

// Profile sau reload là 6s, nhưng request s dùng 1s
// vì s có explicit override.
session.execute(s);
~~~

### 16.5. Rollback và kiểm

1. Khôi phục trong `driver.conf` từ 6 s về 5 s.
2. Reload lại bằng `supportsReloading()`/`reload()`.
3. In `getProfile("history_read").getDuration(REQUEST_TIMEOUT)` phải về 5 s.
4. Thực thi request mới, xác minh SLO/timeout/rate; kiểm hệ thống không tự áp lại 6 s ở lần deploy sau.
5. Đóng session khi ứng dụng kết thúc, không để JMX/driver resources rò rỉ.

**Điểm cần học:** “File đã sửa” khác “config đã reload” và khác “statement đã hết override”. Trong production, không dùng timeout cao hơn để che disk/GC/replica bottleneck mà không có đo lường.

## 17. Derived profiles: thay một request mà không sửa HOCON

### 17.1. Cơ chế

Java Driver 4.x cho tạo **derived execution profile** từ một profile đã tồn tại, bằng các method `withXxx` tạo **object mới**:

~~~java
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.time.Duration;

DriverExecutionProfile base =
    session.getContext().getConfig().getProfile("history_read");

DriverExecutionProfile special =
    base.withDuration(
            DefaultDriverOption.REQUEST_TIMEOUT,
            Duration.ofSeconds(3))
        .withInt(
            DefaultDriverOption.REQUEST_PAGE_SIZE,
            20);

SimpleStatement query = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setExecutionProfile(special)
    .build();

session.execute(query);
~~~

Giá trị được tính:

- `special` dùng timeout **3 s** và page-size **20**.
- Các options khác vẫn đến từ `base` và default profile theo cơ chế inheritance.
- `session.getContext().getConfig().getProfile("history_read")` **không bị sửa trực tiếp** khi tạo `special`.
- Statement dùng **object `special`**, không cần tên mới trong `application.conf`.

### 17.2. Khi nào dùng derived profile?

Phù hợp cho **một use case đặc biệt** hoặc một nhóm nhỏ request cần thử policy trong code. Tuy nhiên:

- `withXxx` tạo object mới; không tạo derived profile **trên từng request** nếu một bản cache dùng lại là đủ.
- Driver phải duy trì linkage khi base profile reload; việc tạo quá nhiều derived profiles làm tăng overhead.
- Nếu nhu cầu ổn định và có hàng ngàn requests/s, **named profile khai báo trước** thường đơn giản và dễ audit hơn.
- Một derived profile có CL đặc biệt vẫn phải đáp ứng consistency contract của nghiệp vụ, không có ngoại lệ vì nó được tạo trong Java.

### 17.3. So sánh named, derived và explicit statement

| Cách chọn | Phù hợp nhất | Độ dễ quan sát/audit | Ví dụ |
|---|---|---|---|
| Named profile | Policy của một query family ổn định | Cao, khai báo HOCON/typed getters | `history_read` |
| Derived profile | Biến thể nhỏ trong code hoặc thử nghiệm | Trung bình, cần ghi code path | `history_read` với timeout 3s và page 20 |
| Explicit request setting | Giá trị ngoại lệ của **một** request | Phải kiểm tại statement | `setTimeout(1s)` |
| Default profile | Request không yêu cầu đặc biệt | Cao, nhưng dễ bị lạm dụng cho mixed workload | CQL health check |

**Tránh “profile explosion”:** Không đặt tên profile theo mỗi tenant ID, mỗi UUID hoặc giá trị query; profile là chính sách cho **lớp truy vấn hữu hạn**, không phải tag theo từng bản ghi.

## 18. Kiểm tra code không phụ thuộc vào Cassandra sống

Một nhóm thường muốn kiểm HOCON/precedence trong CI trước khi mở kết nối. Có thể kiểm config loader ở mức **API**; còn các thử nghiệm liên quan `CqlSession`, routing, timeout thật cần integration tests với cluster lab.

### 18.1. Kiểm default và named profile

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfig;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;
import java.time.Duration;

public final class ConfigContractCheck {
    public static void main(String[] args) {
        DriverConfigLoader loader =
            DriverConfigLoader.fromClasspath("application");

        try {
            DriverConfig config = loader.getInitialConfig();
            DriverExecutionProfile point =
                config.getProfile("point_read");
            DriverExecutionProfile history =
                config.getProfile("history_read");

            Duration pointTimeout = point.getDuration(
                DefaultDriverOption.REQUEST_TIMEOUT);
            Duration historyTimeout = history.getDuration(
                DefaultDriverOption.REQUEST_TIMEOUT);

            if (!pointTimeout.equals(Duration.ofMillis(500))) {
                throw new AssertionError(
                    "point_read timeout differs: " + pointTimeout);
            }
            if (!historyTimeout.equals(Duration.ofSeconds(5))) {
                throw new AssertionError(
                    "history_read timeout differs: " + historyTimeout);
            }
            if (point.getInt(
                    DefaultDriverOption.REQUEST_PAGE_SIZE) != 25) {
                throw new AssertionError("point_read page-size changed");
            }
        } finally {
            loader.close();
        }
    }
}
~~~

Đây là **kiểm config lúc khởi tạo**, không chứng minh cluster sẵn sàng hoặc điều gì xảy ra khi file reload. Nếu CI/JVM có system property override khác, expected values phải được điều chỉnh hoặc môi trường test cần loại bỏ override có kiểm soát. Không sửa tham số runtime production để làm một test pass.

### 18.2. Những test cần integration cluster

| Kiểm thử | Vì sao config-only test chưa đủ? |
|---|---|
| Kết nối tới DC | Phải biết local DC và network/contact points thật |
| `LOCAL_QUORUM` với RF cụ thể | Phải có replica topology và service health |
| Paging nhiều trang | Phải có result set lớn hơn page size |
| LWT với serial CL | Phải có Paxos/contended mutation thật |
| Timeout/retry | Cần mô phỏng độ trễ/failures có kiểm soát |
| Hot reload + request sau reload | Phải giữ session và quan sát behavior |
| Token-aware routing | Phải có prepared statement và partition key/ring đúng |

Không thực hiện các thử nghiệm fault injection (tắt node, làm disk chậm) trên production chỉ để xác nhận profile. Dùng cluster lab/staging có topology đại diện và guardrails đã định.

## 19. Chẩn đoán khi “đã cấu hình nhưng driver vẫn dùng giá trị khác”

### 19.1. Bảng tình huống và cách phân biệt nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Kiểm chứng đúng |
|---|---|---|
| File ghi timeout 1 s, profile in 2 s | File không nằm trong runtime classpath hoặc bị `-D` che | In `DriverConfig`; kiểm JAR/classpath/JVM arguments |
| Tên profile không được tìm thấy | Chưa khai báo, lỗi tên/case, cấu hình load khác file | `config.getProfiles()` và `getProfile(name)` |
| Profile in 500 ms nhưng CQL timeout như 2 s | Statement không chọn profile hoặc explicit override | Kiểm `setExecutionProfileName`/`getTimeout()` |
| Gọi `setTimeout()` mà không đổi | Statement 4.x bất biến, bỏ giá trị trả về | Reassign hoặc dùng builder |
| Named profile timeout 5 s, file default timeout 2 s | **Đúng** inheritance: named override | Đọc cả default và named values |
| Named profile thay đổi khi chưa sửa source | JVM system property, config khác trên classpath, reload | Ghi nguồn config effective và startup args |
| Đổi file sau deploy mà ứng dụng không đổi | Resource trong JAR, reload disabled, custom loader | Xác minh file được đọc, `supportsReloading()` và restart |
| Reload báo changed=true nhưng routing không đổi | Option/policy không runtime-modifiable | Đọc reference option; session rebuild nếu cần |
| Java service gặp `NoNodeAvailable` / init fail | Sai DC/contact points, TLS/auth, cluster down | Kiểm `local-datacenter`, networking/driver logs |
| `LOCAL_QUORUM` timeout khi RF3 có hai replicas DOWN | Không đủ quorum, không phải lỗi merge config | `nodetool status`, RF per DC, coordinator logs |
| `page-size=20` nhưng API đọc 500 rows | Page size **không phải LIMIT** | Đếm pages/rows và xem iterator/fetch behavior |
| p99 xấu dù tăng timeout từ 2 s lên 10 s | Timeout chỉ cho client chờ lâu hơn | Đo queue, disk/GC, replicas, p95/p99 và error budget |
| Timeout vẫn 1 s khi profile reload lên 6 s | Statement có explicit 1 s | Kiểm `Request.getTimeout`/`setTimeout` |
| LWT không đổi khi sửa serial consistency của SELECT profile | Serial CL chỉ có nghĩa với conditional requests | Kiểm CQL `IF` và profile thực của mutation |
| Retry không xảy ra dù `default-idempotence=true` | Policy không retry trường hợp này hoặc statement explicit false | Đọc retry policy, error class, request flag |
| Driver 3.x mẫu code không compile với 4.x | API/classes/setter semantics đã đổi | Chọn tài liệu và dependency **cùng major** |

### 19.2. Sơ đồ điều tra effective value

~~~text
Bạn nghĩ request đang dùng X nhưng hành vi như Y?
                    |
            Session còn sống?
             /             \
           NO               YES
           |                 |
      Debug startup       getContext().getConfig()
      DC/auth/port                |
                         Liệt kê profiles
                                |
                       Named profile tồn tại?
                         /             \
                        NO             YES
                        |               |
                    Sửa tên        In typed values
                                        |
                               Có đúng expected?
                                /            \
                              NO              YES
                              |                |
                       Kiểm precedence    Kiểm statement:
                       -D / program /     profile name?
                       file / reference    explicit setter?
                                             |
                                           Verify
                                      timeout/CL/page
                                             |
                                      Request metrics
                                             |
                                     Cassandra health
~~~

### 19.3. Đọc error logs mà không lộ dữ liệu

Trong môi trường phát triển, có thể bật logging của driver/Typesafe config theo cơ chế logging framework để xem nơi nạp file, cảnh báo profile và failures. Nhưng:

- **Không** log raw CQL bind values hoặc password khi không cần thiết.
- Hạn chế quyền xem logs; thông tin liên quan authentication/truststore/config file paths cũng nhạy cảm.
- Gắn marker khi deploy/reload; tránh gộp logs từ instance cũ và instance canary mới.
- Nếu server cảnh báo “slow query”, xem cả node/replica/compaction/partition key; không vội kết luận config loader gây ra.

### 19.4. Check một option từ nhiều profile

Một diagnostic nhỏ thay vì chỉ in default:

~~~java
DriverConfig config = session.getContext().getConfig();
config.getProfiles().forEach((name, profile) -> {
    System.out.printf(
        "profile=%s timeout=%s consistency=%s pageSize=%d%n",
        name,
        profile.getDuration(DefaultDriverOption.REQUEST_TIMEOUT),
        profile.getString(DefaultDriverOption.REQUEST_CONSISTENCY),
        profile.getInt(DefaultDriverOption.REQUEST_PAGE_SIZE));
});
~~~

`getProfiles()` trả các profiles đã biết bao gồm default, giúp phát hiện cấu hình sai tên. Nhưng nó vẫn **không chứng minh repository method đã gọi đúng profile**; cần code review/instrumentation statement hoặc integration test theo query family.

## 20. Observability: effective config là một chiều, hiệu quả request là chiều khác

### 20.1. Bật một số driver metrics có chọn lọc

Theo Java Driver 4.17, các metrics driver **bị tắt mặc định**, cần bật đúng loại và chọn metrics library/reporter phù hợp:

~~~hocon
datastax-java-driver {
  advanced.metrics {
    session.enabled = [
      connected-nodes,
      cql-requests,
      cql-client-timeouts
    ]
    node.enabled = [
      cql-messages,
      pool.open-connections,
      pool.in-flight
    ]
  }
}
~~~

Tên metric xuất ra Prometheus/Dropwizard/Micrometer phụ thuộc integration; chỉ bật option trong HOCON **không tự tạo dashboard** khi thiếu registry/exporter. Trước khi dùng metrics cho một quyết định rollback, phải kiểm metrics thực có được scrape hay không.

### 20.2. Phân biệt metrics phía driver

| Metric | Scope | Diễn giải |
|---|---|---|
| `cql-requests` | Session | Tổng latency và throughput của CQL requests, bao gồm retry theo semantics driver |
| `cql-client-timeouts` | Session | Request vượt deadline driver |
| `connected-nodes` | Session | Số nodes có active connection |
| `cql-messages` | Node | Messages/attempts gửi đến node; một request logic có thể tạo nhiều message do retry/speculation |
| `pool.open-connections` | Node | Kết nối tới node |
| `pool.in-flight` | Node | Messages đang chờ phản hồi |

Với ứng dụng Java đa service, metrics session này thường **không biết tên CQL template/feature**. Để xem một profile ảnh hưởng query nào, instrument ở repository bằng **query family** hữu hạn, outcome, local DC và profile name; không dùng raw SQL, tenant ID, UUID hoặc email làm metric labels vì high-cardinality và rủi ro riêng tư.

### 20.3. Giám sát server song song

~~~bash
nodetool status
nodetool tpstats
nodetool tablestats driver_lab.events_by_tenant_day
nodetool compactionstats
nodetool netstats
~~~

| Driver observation | Server observation có ích | Giả thuyết |
|---|---|---|
| `cql-requests` p99 tăng | `ClientRequest.Read.Latency` tăng | Coordinator/replica/storage chậm |
| `pool.in-flight` tăng, node healthy | App concurrency/throttle và CPU client | Có thể là client-side queue |
| `cql-messages`/`cql-requests` tăng | Server requests, timeouts tăng | Retry/speculation khuếch đại tải |
| Một named profile bị timeout | Table tombstones/SSTables-per-read cao | Query shape hoặc partition size |
| Nhiều family cùng chậm | Disk/GC/compaction cùng tăng | Bottleneck chung, không phải mọi profile sai |
| `connected-nodes` giảm | Node DOWN, network/TLS/repair | Availability/topology issue |

**Không lấy hiệu hai p99** của driver/server để suy chính xác network latency: percentiles từ hai tập không đồng nhất không có phép trừ đơn giản. Khi cần phân rã, dùng tracing và event timelines của cùng request.

### 20.4. Đo hiệu quả sau thay profile

Tạo hai nhóm canary/control hợp lý:

~~~text
Canary 5% instances:
  history_read timeout 5s -> 6s

Control 95% instances:
  history_read timeout = 5s

Đo cùng window/workload:
  request count, p95/p99, error/timeout%
  page counts, retries, pool in-flight
  coordinator/replica latency, CPU/disk/GC
  consistency correctness, business outcome
~~~

Đây chỉ là **mô hình thí nghiệm**, không mặc định 5% luôn an toàn. Khi mỗi instance gửi traffic tới **cùng cluster Cassandra**, canary và control **có thể ảnh hưởng nhau qua tài nguyên chung**, nên phải theo dõi cả server. Timeout cao hơn có thể tăng số request đang giữ connection/in-flight hoặc làm request error rate trông ít hơn trong khi user experience xấu.

### 20.5. Giữ source-of-truth cho config

Mỗi release nên ghi **non-secret config fingerprint**:

~~~text
service: order-api
driver: 4.17.x
java: 17
cluster / local DC: cassandra-orders / dc1
config source: external /etc/order-api/driver.conf
config commit/version: abc123
default: timeout 3s / CL LOCAL_QUORUM / page 500
point_read: timeout 800ms / page 50
history_read: timeout 8s / page 200
reload enabled: yes/no, interval
~~~

Không ghi password/truststore secrets. Nếu system properties khác với Git config, phải ghi **effective values** và biết ai đã inject override; nếu không, lần rollback có thể thay file nhưng không thay runtime.

## 21. Runbook production: deploy, reload, verify và rollback

### 21.1. Preflight trước khi đổi một profile

Một thay đổi cấu hình request trong Java nên có:

1. **Mục tiêu định lượng:** Ví dụ giảm tỷ lệ timeout của `orders.listRecent` mà không tăng p99 hay số request đang chờ vượt SLO.
2. **Phạm vi:** Service, JVM instances, cluster/DC, profile name, release/config commit.
3. **Giá trị C0 effective:** Đọc từ `DriverConfig`, kiểm cả explicit attributes của statement.
4. **Giá trị C1 dự kiến:** Có đơn vị, hợp đồng consistency và rollback plan.
5. **Nguồn override:** `-D`, programmatic loader, file ngoài JAR hay packaged resource.
6. **Reload feasibility:** Option có runtime-modifiable không; loader có `supportsReloading` không.
7. **Metrics:** App p95/p99/error, driver session/node, Cassandra coordinator/table, replica health.
8. **Bảo toàn dữ liệu:** Không đổi CL/idempotence/TTL/timestamp semantics vô ý.

### 21.2. Thực thi theo pha

~~~text
T0: Chụp baseline, config source/version, C0 effective
    |
T1: Canopy preflight: DC, RF, cluster health, traffic
    |
T2: Phát C1 trên 1 canary instance/profile
    |
T3: Reload nếu đúng loại option; hoặc redeploy session
    |
T4: In C1 effective, kiểm statement không có override bất ngờ
    |
T5: Quan sát requests mới và server đủ mẫu
    |
T6: Quyết định GO / HOLD / ROLLBACK / ESCALATE
    |
T7: Mở rộng từng batch nếu GO, lặp lại T4-T6
    |
T8: Chốt config management và hiệu lực toàn service
~~~

Trong pha có cấu hình cần session rebuild, rollout cũng có thể gây **connection storm/reprepare** hoặc warmup; không khởi động lại tất cả JVM/replicas cùng lúc chỉ vì một profile.

### 21.3. Ví dụ guardrails (tất cả số minh họa)

| Chỉ số | Baseline | Trigger canary minh họa | Hành động |
|---|---:|---:|---|
| `history_read` p99 | 350 ms | `>600 ms` trong 3 cửa sổ đủ mẫu | Dừng mở rộng/rollback |
| Timeout rate | 0,1% | `>1%` trong hai cửa sổ 5 phút | Rollback hoặc incident |
| Driver pool in-flight | 80 | Tăng kéo dài trên nhiều node, throughput không tăng | HOLD/điều tra |
| `cql-messages`/`cql-requests` | ~1 ở workload mẫu | Tăng bất thường với retry/speculation | Điều tra attempts/idempotence |
| Replica availability | Đủ quorum | Không còn đủ CL yêu cầu | **ESCALATE ngay** |
| Disk await/GC | Ổn định | Bất thường kéo dài tương quan traffic canary | Không tiếp tục |
| Correctness | Kết quả từ audit khớp | Sai hàng/CL không được duyệt | **STOP**, không chỉ đổi timeout |

Đây **không phải ngưỡng chuẩn của Cassandra**. Điều kiện phải theo SLO/resource của hệ thống và sample count; với lỗi data/quorum nghiêm trọng, không chờ đủ 3 cửa sổ.

### 21.4. Rollback config khác rollback request

- **Rollback config:** đổi file/flag/code trở lại `C0`, reload hoặc redeploy, in effective values.
- **In-flight requests:** request đã gửi với config C1 có thể đang chạy; rollback không tự “rút lại” mọi request.
- **Write outcome:** timeout/retry lúc thử C1 có thể để lại write đã thực thi; cần reconcile theo idempotency/business event nếu nghi vấn.
- **Data/schema:** nếu đợt thử còn thay CQL/schema/CL khác, chỉ rollback driver config **không** khôi phục data/migration.
- **Source-of-truth:** loại bỏ override `-D`/programmatic cũ hoặc thay đúng file manager để restart sau không tự áp C1.

### 21.5. Phiếu xác nhận hậu thay đổi

~~~text
CHANGE: ORDER-DRIVER-PROFILE-002 (ví dụ)
SERVICE / LOCAL DC: order-api / dc1
PROFILE: history_read
OPTION: REQUEST_TIMEOUT
OLD EFFECTIVE C0: 5 s
NEW PROPOSED C1: 6 s
LOADER: fromFile(/etc/order-api/driver.conf)
PER-STATEMENT OVERRIDE: none for listRecent
RELOAD: supported / attempted / changed=true
CANARY: 1 instance, period and request samples recorded
APP: p95/p99, timeout%, user-visible failures
DRIVER: cql-requests, cql-messages, pool.in-flight
SERVER: ClientRequest, Table latency, disk/GC/repair
DECISION: GO / HOLD / ROLLBACK / ESCALATE
POST-ACTION EFFECTIVE VALUE: C1 or C0 (verified)
RESIDUAL RISKS / OWNER: ...
~~~

**Không** đánh dấu `ROLLED_BACK` chỉ vì file đã được sửa; phải kiểm C0 từ `DriverConfig` và hậu quả request đã trở về mức chấp nhận được.

## 22. Tám tình huống thực tế và cách ra quyết định

### Ca A — `application.conf` ghi 500 ms, service lại dùng 5 s

**Dấu hiệu:** Source code/HOCON chứa `point_read.timeout=500 ms`, nhưng startup diagnostics in `PT5S`.

**Giả thuyết:** Deployment có `-Ddatastax-java-driver.profiles.point_read.basic.request.timeout="5 seconds"` hoặc programmatic override.

**Cách xử lý:** In source path/version của loader, kiểm JVM flags và typed getter. Nếu property được deploy platform đưa vào, sửa **đúng source-of-truth** của nó; chỉ đổi `application.conf` không thắng `-D`. Sau rollback, kiểm một request mới không bị statement-level override.

### Ca B — Named profile đúng, nhưng repository vẫn timeout như default

**Dấu hiệu:** `getProfile("history_read")` in 5 s, nhưng request log thấy timeout 2 s.

**Nguyên nhân khả dĩ:** Repository không đặt `setExecutionProfileName("history_read")` trên statement **thực sự truyền vào `session.execute`**; hoặc gọi setter nhưng bỏ giá trị trả về trên immutable statement.

**Cách xử lý:** Đọc code path của statement được execute, viết integration test kiểm profile selection. Không tăng global default lên 5 s để che lỗi chọn profile.

### Ca C — Profile đang dùng đúng nhưng CL yêu cầu làm query unavailable

**Dấu hiệu:** RF3 tại dc1, profile `write_critical` đặt `LOCAL_QUORUM`. Một node DOWN, một node khác chưa phục hồi; query trả `Unavailable`.

**Giải thích:** Với RF3, local quorum cần 2 full replicas có thể phản hồi; nếu thực tế chỉ còn 1, thay timeout 2 s → 20 s không tạo thêm replica.

**Quyết định:** Incident availability/topology, khôi phục node hoặc điều phối traffic theo runbook. Không tự hạ CL xuống ONE để “fix” dữ liệu trọng yếu khi hợp đồng không cho phép.

### Ca D — Tăng `history_read.page-size` giảm round trip nhưng tăng memory

**Dấu hiệu:** Page-size từ 100 → 5.000 giúp một vài GET /history trả nhanh hơn trong lab. Production nhiều rows/columns lớn lại tăng response bytes, client heap và GC; p99 các APIs khác xấu.

**Quyết định:** Rollback hoặc thử page size trung gian theo workload; kiểm rows/page, bytes/page, total pages/API và application memory. Cân nhắc cursor API/giới hạn kết quả thay vì dồn cả dataset vào một page.

### Ca E — Default idempotence bật true và tạo retry storm

**Dấu hiệu:** Một developer bật `basic.request.default-idempotence=true` toàn service và speculative execution/reroute policy. Client latency cải thiện ngắn hạn nhưng node `cql-messages`, CPU, write conflicts và timeout khác tăng.

**Nguy cơ:** Mixed workloads có counter, LWT, TTL và mutation gắn UUID mới. Gắn idempotent=true cho request không thực sự idempotent có thể gây duplicate/incorrect state.

**Quyết định:** Quay về default false theo hợp đồng, đặt idempotence explicit cho những family đã review, đo retry/attempts và correctness. Không coi flag là một tối ưu “miễn phí”.

### Ca F — Profile hot reload thành công nhưng request cũ không đổi

**Dấu hiệu:** Typed getter của `history_read` từ 5 s → 6 s, nhưng một số request đang chạy vẫn timeout theo 5 s.

**Giải thích:** Runtime-modifiable settings áp dụng cho **requests mới**; không yêu cầu mọi in-flight requests tự thay deadline. Một số statements còn có `setTimeout(1s)` tường minh.

**Quyết định:** Quan sát phân phối request sau reload và in-flight; không restart tất cả services ngay vì một số mẫu cũ. Nếu cần thay resource/policy không reloadable, lập deployment plan riêng.

### Ca G — Mỗi request tạo một derived profile

**Dấu hiệu:** Hot path với 10.000 QPS tạo `base.withDuration(...)` từ thông tin tenant cho từng query.

**Nguy cơ:** Hàng nghìn objects/profiles, overhead reloading và khó theo dõi policy. Nếu giá trị lấy từ đầu vào tùy ý, timeout có thể không còn giới hạn tập hữu hạn.

**Quyết định:** Dùng một số named profiles được định nghĩa trước hoặc cache vài derived profiles đã kiểm. Đặt deadline theo business requirement và cap, không để request tự chọn unlimited timeout.

### Ca H — Đổi profile timeout “cải thiện” tỉ lệ timeout nhưng API vẫn chậm

**Dấu hiệu:** Timeout tăng từ 2 lên 10 s, tỉ lệ `DriverTimeoutException` giảm, nhưng p99 API tăng và nhiều request giữ pool in-flight lâu hơn.

**Giải thích:** Driver đợi lâu hơn, không chứng minh Cassandra nhanh hơn. Có thể query thiếu partition key, tombstones nhiều, compaction backlog hoặc node network không ổn.

**Quyết định:** So với SLO end-to-end, kiểm server/driver metrics, xử lý query shape/capacity. Đặt rollback threshold trước khi tiếp tục tăng timeout.

## 23. Checklist áp dụng trong dự án Java Cassandra

### 23.1. Khi viết cấu hình ban đầu

- [ ] Java Driver **major/version** đã xác định; tài liệu/API cùng phiên bản.
- [ ] Có `CqlSession` được tái sử dụng, không tạo từng request.
- [ ] Biết config loader mặc định/`fromFile`/programmatic/custom đang dùng.
- [ ] Đã xác nhận source precedence: `-D`, programmatic, application resources và reference.
- [ ] Root HOCON đúng `datastax-java-driver`, không sai prefix.
- [ ] Contact points và `local-datacenter` khớp topology thật.
- [ ] RF của keyspace và normal/serial CL có review.
- [ ] Default request timeout/page/idempotence có giá trị rõ ràng.
- [ ] Named profiles phân theo policy/query family ổn định, không theo user/tenant key.
- [ ] Mỗi named profile chỉ override những options cần khác default.
- [ ] Các options được override trong profile thực sự được reference đánh dấu hỗ trợ.
- [ ] Không đặt `default-idempotence=true` toàn bộ mixed write workloads khi chưa audit.
- [ ] Credential/TLS config dùng secret management, không ghi full resolved config vào logs.

### 23.2. Khi viết repository/service

- [ ] CQL có partition key/access pattern phù hợp Cassandra wide-column.
- [ ] PreparedStatement dùng cho query lặp lại, bind key/type đúng.
- [ ] Code chọn đúng `setExecutionProfileName` và không bỏ instance trả về.
- [ ] Không tạo `DriverExecutionProfile.withXxx` trên mỗi request khi có thể dùng named/cache.
- [ ] Explicit `setTimeout`/`setConsistencyLevel`/`setPageSize` là ngoại lệ được review.
- [ ] Không dùng page size như LIMIT/tổng số rows.
- [ ] Có end-to-end API deadline nếu truy vấn nhiều pages.
- [ ] Retry/speculative execution chỉ áp dụng khi idempotency được xác nhận.
- [ ] Kiểm unknown write outcome sau timeout thay vì mặc định retry an toàn.
- [ ] Normal CL và serial CL của LWT được phân biệt rõ.
- [ ] Mỗi query family có metrics success/failure, p95/p99 và timeout.

### 23.3. Khi thay config production

- [ ] Đã lưu **effective C0** từ chính JVM, không chỉ từ file.
- [ ] Đã ghi version/source/path của loader và startup overrides.
- [ ] Thay đúng option, đúng profile và đúng scope.
- [ ] Biết runtime-modifiable hay cần session rebuild/redeploy.
- [ ] Nếu hot reload, kiểm `supportsReloading` và `reload` result.
- [ ] Sau reload đã đọc typed getters và kiểm explicit statement override.
- [ ] Đã kiểm traffic đủ mẫu, query families và error budget.
- [ ] Giám sát cql-requests/cql-messages, in-flight, node/timeouts và server disk/GC.
- [ ] Không thay CL/idempotence hoặc request retry để đổi hiệu năng mà thiếu correctness review.
- [ ] Có canary, rollback trigger và source-of-truth config quản lý tập trung.
- [ ] Khi rollback, effective C0 **và** SLO/resource đã được kiểm hồi phục.

### 23.4. Khi debug “config sai”

- [ ] In `session.getContext().getConfig().getProfiles()`.
- [ ] In `REQUEST_TIMEOUT`/`REQUEST_CONSISTENCY`/`REQUEST_PAGE_SIZE` theo profile.
- [ ] Kiểm named profile name đúng spelling/case.
- [ ] Kiểm statement có đang chọn profile đó không.
- [ ] Kiểm explicit request settings có ghi đè không.
- [ ] Kiểm `-D` trên **đúng JVM**, file classpath và programmatic builder.
- [ ] Kiểm có reload thực và option hỗ trợ runtime không.
- [ ] Kiểm local DC/replica availability trước khi quy mọi timeout cho config.
- [ ] Kiểm application/framework integration có tạo session khác ngoài ý muốn.
- [ ] Không ghi secrets hoặc raw bind values trong debug output.

## 24. Câu hỏi tự đánh giá và gợi ý đáp án

**Câu 1.** `reference.conf` và `application.conf` khác nhau như thế nào?  
**Định hướng:** `reference.conf` do driver JAR cung cấp defaults; `application.conf` chứa overrides của ứng dụng và thường nằm trong runtime classpath.

**Câu 2.** Khi cả `application.conf` và `-Ddatastax-java-driver.basic.request.timeout` khai báo cùng option, ai ưu tiên?  
**Định hướng:** System property có ưu tiên cao hơn trong default loader.

**Câu 3.** Khi `programmaticBuilder` đặt 3 s nhưng JVM `-D` đặt 4 s cho cùng option, effective default timeout là bao nhiêu?  
**Định hướng:** 4 s, vì system properties ưu tiên hơn programmatic overrides trong loader này.

**Câu 4.** Có `fromFile("/etc/my-driver.conf")`. Driver tự đọc thêm mọi `application.conf` trên classpath không?  
**Định hướng:** Không theo mặc định; `fromFile` dùng system properties → file chỉ định → reference.conf.

**Câu 5.** Default profile timeout 2 s, named `history_read` timeout 5 s. Khi request dùng `history_read` nhưng không ghi timeout, kết quả là gì?  
**Định hướng:** 5 s.

**Câu 6.** Trong câu 5, statement còn `setTimeout(Duration.ofSeconds(1))`. Request dùng bao nhiêu?  
**Định hướng:** 1 s vì explicit statement timeout thắng profile.

**Câu 7.** Named profile `point_read` chỉ ghi timeout, không ghi CL. Nó dùng CL từ đâu?  
**Định hướng:** Kế thừa default profile **đã merge** từ các nguồn config.

**Câu 8.** Gọi `s.setExecutionProfileName("point_read"); session.execute(s);` trong driver 4.x có nguy cơ gì?  
**Định hướng:** Built-in statements immutable; bỏ instance trả về nên `s` cũ vẫn không có profile mới.

**Câu 9.** `config.getProfile("unknown")` cho gì?  
**Định hướng:** Có thể ném `IllegalArgumentException`; nên xác nhận profile trong startup/tests.

**Câu 10.** `getProfile("history_read").getDuration(REQUEST_TIMEOUT)` trả 5 s, request có `setTimeout(1s)`. Giá trị 5 s có chứng minh request đang dùng 5 s không?  
**Định hướng:** Không; typed getter của profile không thấy explicit override của statement.

**Câu 11.** `getString(REQUEST_CONSISTENCY)` phù hợp hơn `getInt(REQUEST_CONSISTENCY)` vì sao?  
**Định hướng:** Option này có value type String; typed getters phải khớp loại được định nghĩa trong `DefaultDriverOption`.

**Câu 12.** Vì sao `page-size=25` không phải `LIMIT 25`?  
**Định hướng:** Page size quyết định kích thước fetch từng trang; iterator có thể fetch hết nhiều trang.

**Câu 13.** Một service đặt `page-size=5.000` và gặp out-of-memory khi duyệt kết quả lớn. Đổi timeout thấp có giải quyết gốc không?  
**Định hướng:** Không; cần giới hạn kết quả, paging/cursor, data model, xử lý streaming và kiểm client memory.

**Câu 14.** Khi RF=3 tại một DC và `LOCAL_QUORUM`, số replica phản hồi thông thường cần là bao nhiêu?  
**Định hướng:** 2 full replicas trong local DC; nếu chỉ 1 khỏe, request có thể unavailable.

**Câu 15.** Tại sao không chọn `LOCAL_ONE` cho thao tác thanh toán chỉ vì p99 thấp hơn `LOCAL_QUORUM`?  
**Định hướng:** CL là hợp đồng dữ liệu, không chỉ tùy chọn performance; phải đánh giá consistency/durability theo nghiệp vụ.

**Câu 16.** `SERIAL`/`LOCAL_SERIAL` có tác dụng gì khác với normal CL?  
**Định hướng:** Chúng liên quan conditional mutations/LWT/Paxos; không thay normal CL và không giúp point SELECT thông thường.

**Câu 17.** `default-idempotence=true` có làm counter increment idempotent không?  
**Định hướng:** Không. Flag giúp driver quyết định retry/speculation; lặp increment có thể tăng nhiều lần.

**Câu 18.** Timeout của `session.execute()` đã bao gồm retries; điều đó có phải một deadline end-to-end cho API đọc 100 pages không?  
**Định hướng:** Không mặc định; các page fetch tiếp là những requests, API cần total deadline/cursor/limit riêng.

**Câu 19.** Vì sao sửa `src/main/resources/application.conf` trên laptop không đổi ngay JVM đang chạy JAR?  
**Định hướng:** Resource runtime đã được đóng gói/đang ở classpath khác; cần deploy file mới hoặc dùng external config + reload hợp lệ.

**Câu 20.** Khi `DriverConfigLoader.fromString` được dùng, có thể chắc chắn hot reload như `fromFile` không?  
**Định hướng:** Không; loader fromString trong API 4.17 không hỗ trợ runtime reload.

**Câu 21.** `reload()` trả `true` có chứng minh protocol version/load balancing policy được tái khởi tạo không?  
**Định hướng:** Không; `true` là config change, một số options không runtime-modifiable.

**Câu 22.** Named profile timeout 5 s được reload thành 6 s nhưng request vẫn 1 s. Hai nguyên nhân phổ biến?  
**Định hướng:** Explicit `setTimeout(1s)` hoặc system property nhắm đúng profile áp giá trị ưu tiên cao hơn.

**Câu 23.** Vì sao tạo derived profile mới cho mỗi request ở 10.000 QPS là không tốt?  
**Định hướng:** Object/config overhead và reload propagation; ưu tiên named profiles hoặc cache một số derived profiles.

**Câu 24.** Một session driver có nhiều execution profiles có phải tương đương nhiều cluster Cassandra riêng không?  
**Định hướng:** Không. Các profiles là request policies; chúng cùng chia sẻ cluster/tài nguyên trừ các cơ chế policy riêng thực sự được cấu hình.

**Câu 25.** `cql-requests` khác `cql-messages` ra sao?  
**Định hướng:** Session-level CQL requests khác per-node message attempts; retries/speculation có thể tạo nhiều messages cho một request.

**Câu 26.** P95 của `history_read` cao nhưng typed getter cho timeout đúng. Bước tiếp theo?  
**Định hướng:** Đo query shape/partition keys, request retry/page counts, coordinator/replica/table metrics, disk/GC và data correctness, không chỉ sửa config.

**Câu 27.** Vì sao không nên log toàn bộ config object khi debug?  
**Định hướng:** Có thể lộ credentials, TLS truststore/key paths, contact points và thông tin nhạy cảm; chỉ log allowlisted values.

**Câu 28.** Thay local DC bằng profile khác có đủ để chuyển một service từ dc1 sang dc2 an toàn không?  
**Định hướng:** Không. Local DC thuộc session/load balancing setup và cần topology/replication/readiness/network/traffic plan, không chỉ per-query timeout profile.

**Câu 29.** Muốn rollback timeout 6 s → 5 s, điều kiện nào chứng minh hoàn thành?  
**Định hướng:** Config manager đã trả C0, reload/redeploy có hiệu lực, typed getter là 5 s, statement overrides được kiểm và SLO/timeout behavior phục hồi.

**Câu 30.** Query dùng prepared statement có partition key nhưng p99 vẫn lớn. Execution profile có giải quyết chắc chắn không?  
**Định hướng:** Không; có thể là partition quá rộng, tombstones, SSTables, disk/GC hoặc node outage. Chỉ chỉnh timeout/page size không thay data model.

## 25. Tổng kết: công thức xác định effective value

~~~text
                     DRIVER 4.x CONFIG
                            |
               +------------+------------+
               |                         |
        SOURCE PRECEDENCE           RUNTIME LOADER
        system properties           có reload không?
             > programmatic         option modifiable?
             > app.conf
             > app.json
             > app.properties
             > reference.conf
               |                         |
               +------------+------------+
                            |
                     DEFAULT PROFILE
                            |
             +--------------+---------------+
             |                              |
      Request không profile          Named/derived profile
             |                       kế thừa default
             |                        + override
             +--------------+---------------+
                            |
                  EXPLICIT STATEMENT OPTIONS?
                      /              \
                    YES              NO
                    |                 |
                 Override        Profile value
                    \                 /
                     \               /
                       EFFECTIVE REQUEST
                            |
                  CQL Coordinator/Replicas
                            |
              Quan sát latency/CL/paging/errors
                     và correctness
~~~

Một cách ghi nhớ ngắn:

\[
\text{EffectiveOption(request)}
=
\begin{cases}
\text{StatementOverride}, & \text{nếu được đặt tường minh},\\
\text{Named/DerivedProfile}, & \text{nếu chọn và override option},\\
\text{DefaultProfile đã resolve}, & \text{nếu còn lại}.
\end{cases}
\]

Lưu ý đây là **mô hình cho những request options có hỗ trợ override**, không phải công thức chung cho mọi option của driver (ví dụ local DC, Netty timer hoặc protocol version không được giải quyết như per-request settings).

**Thông điệp quan trọng nhất:** Đừng hỏi “file `application.conf` ghi gì?” rồi coi đó là đáp án cuối cùng. Hãy hỏi **session đang dùng loader nào, các nguồn đã merge ra sao, request chọn profile nào và statement đã override gì**. Sau đó kiểm bằng `DriverConfig.getProfile()`/typed getters và request metrics. Chỉ khi đối chiếu đủ các lớp, bạn mới có thể thay timeout, consistency, page size hoặc idempotence mà không ngẫu nhiên thay đổi hành vi phân tán và tính đúng dữ liệu của Cassandra.

## Tài liệu tham khảo

- [Apache Cassandra Java Driver 4.18 — Configuration](https://apache.github.io/cassandra-java-driver/4.18.0/core/configuration/) — cấu trúc Typesafe Config, execution profiles, typed getters, reload và derived profiles (Apache-maintained từ 4.18).
- [DataStax Java Driver 4.17 — Configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/) — HOCON/application.conf, profile inheritance, config precedence, programmatic builder, reload.
- [DataStax Java Driver 4.17 — Reference Configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/reference/) — defaults và metadata “modifiable at runtime / overridable in a profile” cho từng option.
- [DataStax Java Driver 4.17 — DriverConfigLoader API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/config/DriverConfigLoader.html) — `fromFile`, `fromClasspath`, `programmaticBuilder`, `supportsReloading`/`reload`.
- [DataStax Java Driver 4.17 — DriverConfig API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/config/DriverConfig.html) — `getDefaultProfile`, `getProfile`, `getProfiles`.
- [DataStax Java Driver 4.17 — DriverExecutionProfile API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/config/DriverExecutionProfile.html) — typed getters/`withXxx`, derived profiles và immutability.
- [DataStax Java Driver 4.17 — DefaultDriverOption API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/config/DefaultDriverOption.html) — các constant `REQUEST_TIMEOUT`, `REQUEST_CONSISTENCY`, `REQUEST_PAGE_SIZE`, `REQUEST_DEFAULT_IDEMPOTENCE`.
- [DataStax Java Driver 4.17 — Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/) — `SimpleStatement`, `BoundStatement`, bất biến, request attributes và overrides.
- [DataStax Java Driver 4.17 — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/) — page size, auto/async fetch và giới hạn bộ nhớ.
- [DataStax Java Driver 4.17 — Retries](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/retries/) — retry policy và timeout/unknown write outcome.
- [DataStax Java Driver 4.17 — Query Idempotence](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/idempotence/) — quyết định request idempotent cho retry/speculative execution.
- [DataStax Java Driver 4.17 — Speculative Execution](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/speculative_execution/) — khả năng giảm tail latency và chi phí requests bổ sung.
- [DataStax Java Driver 4.17 — Metrics](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metrics/) — `cql-requests`, `cql-messages`, `pool.in-flight`, kết nối registry.
- [Apache Cassandra — Replication and consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — token ring, natural replicas, coordinator, quorum và consistency.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — partition key và truy vấn theo wide-column design.
- [Apache Cassandra — CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — SELECT, INSERT/IF, paging, timestamp và hạn chế truy vấn.

