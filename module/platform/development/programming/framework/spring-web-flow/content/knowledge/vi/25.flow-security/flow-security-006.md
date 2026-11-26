# Tùy chỉnh AuthorizationManager trên các phiên bản hỗ trợ

Spring Web Flow (SWF) cho phép bảo vệ **flow, state và transition** bằng phần tử `secured` trong flow XML. Khi ứng dụng chỉ dùng role thông thường, manager mặc định dựa trên authority của Spring Security có thể đáp ứng. Nhưng nhiều hệ thống cần kiểm tra quyền theo **permission**, tenant, loại tài nguyên hoặc chính sách nghiệp vụ. Khi đó, ta cần tùy chỉnh `AuthorizationManager` để quyết định người dùng hiện tại có được vào một flow, state hoặc thực hiện transition hay không.

Bài thuộc chương **Bảo vệ flow** của module `SPRING_WEB_FLOW`. Trọng tâm là hook `SecurityFlowExecutionListener#setAuthorizationManagerInitializer`, hợp đồng của `AuthorizationManager`, cách đọc `SecurityRule`, chọn manager theo từng quy tắc, và khác biệt API giữa các dòng Spring Security. Ta cũng sẽ phân biệt bảo vệ flow với bảo vệ URL và method, vì một lớp kiểm tra không thể thay thế mọi lớp còn lại.

Ví dụ lấy **Spring Web Flow 3.0.2 + Spring Framework 6.x + Spring Security 6.x** làm nền tảng. Phần đối chiếu phiên bản bao gồm Web Flow 2.5.x, 3.0.0, 3.0.1/3.0.2 và 4.0.x; Spring Security 5.5+, 6.4+ và 7.x. Hãy dùng dependency management của ứng dụng để xác nhận tổ hợp thực tế trước khi áp dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của `AuthorizationManager` và sự khác nhau với `AccessDecisionManager`.
2. Xác định phiên bản Web Flow có hỗ trợ hook `setAuthorizationManagerInitializer`.
3. Hiểu khác biệt giữa `AuthorizationManager#check` và `AuthorizationManager#authorize`.
4. Khai báo bảo vệ flow, state và transition bằng phần tử `secured`.
5. Đăng ký `SecurityFlowExecutionListener` vào `FlowExecutor`.
6. Viết manager riêng dựa trên `SecurityRule`, `Authentication` và permission nghiệp vụ.
7. Xử lý chính sách `any`/`all`, người dùng chưa đăng nhập và quyền không tồn tại theo hướng fail-closed.
8. Phân biệt authorization của flow với request authorization, method security và kiểm tra quyền trên dữ liệu.
9. Kiểm thử trường hợp được phép, bị từ chối, event không hợp lệ và lỗi authorization bị nuốt.
10. Lập kế hoạch chuyển từ `AccessDecisionManager` sang `AuthorizationManager` theo phiên bản.

## 2. AuthorizationManager giải quyết vấn đề gì?

Trong Spring Security, **authentication** trả lời “người dùng là ai?”, còn **authorization** trả lời “người dùng đó được phép làm gì?”. Một đối tượng `Authentication` đang có trong `SecurityContext` thường chứa principal và các `GrantedAuthority`.

`AuthorizationManager<T>` nhận:

- `Supplier<Authentication>`: nguồn cung cấp danh tính hiện tại, được đọc khi cần.
- `T object`: đối tượng/ngữ cảnh đang được kiểm tra.
- Kết quả quyết định: cho phép hoặc từ chối truy cập.

Từ Spring Security 5.5, `AuthorizationManager` được giới thiệu như một API mới cho authorization ở tầng web/filter; Spring Security 5.6 mở rộng API này sang method security. Nó được thiết kế để thay thế dần mô hình `AccessDecisionManager` và `AccessDecisionVoter`.

| API | Mục đích |
| --- | --- |
| `Authentication` | Danh tính và authorities của người dùng |
| `GrantedAuthority` | Một quyền/authority được cấp |
| `AuthorizationManager<T>` | Quyết định truy cập với ngữ cảnh kiểu T |
| `AuthorizationDecision` | Kết quả allow/deny theo boolean |
| `AuthorizationResult` | Hợp đồng kết quả tổng quát ở các phiên bản mới |
| `SecurityRule` (Web Flow) | Danh sách thuộc tính bảo mật và kiểu so khớp |
| `SecurityFlowExecutionListener` | Chạy kiểm tra khi flow/state/transition được bảo vệ |

### 2.1. AuthorizationManager không phải AuthenticationManager

Hai tên gần giống nhưng trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `AuthenticationManager` | Xác thực credential và tạo `Authentication` | Kiểm tra username/password |
| `AuthorizationManager` | Quyết định một `Authentication` có được truy cập tài nguyên hay không | Có permission `booking:confirm` không? |

Không gọi `AuthenticationManager` để kiểm tra quyền trên một transition. Khi flow đã được Spring Security xác thực, `SecurityFlowExecutionListener` dùng `Authentication` hiện tại để thực hiện authorization.

### 2.2. AuthorizationManager có thể kiểm tra dữ liệu nào?

Một manager có thể dựa trên authority đơn giản:

~~~java
boolean granted = authentication.getAuthorities().stream()
    .anyMatch(authority -> "booking:read".equals(authority.getAuthority()));
~~~

Hoặc gọi policy service để đánh giá tenant, chủ sở hữu, trạng thái hồ sơ, thời gian hiệu lực hay quy tắc từ một policy engine. Với các điều kiện phụ thuộc **một bản ghi nghiệp vụ cụ thể**, service xử lý bản ghi đó vẫn phải kiểm tra quyền tại thời điểm thao tác. Không nên giả định đối tượng `Object` mà flow listener truyền cho manager luôn là entity booking hoặc đối tượng form.

## 3. Phiên bản nào hỗ trợ hook tùy chỉnh của Web Flow?

Đây là điểm phải kiểm tra trước khi viết code. Spring Security có `AuthorizationManager` từ 5.5, nhưng **không có nghĩa mọi phiên bản Spring Web Flow đều có API tích hợp manager này**.

| Spring Web Flow | Tích hợp bảo mật của `SecurityFlowExecutionListener` | Cách tùy chỉnh |
| --- | --- | --- |
| 2.5.x | Dùng `AccessDecisionManager`; không có `setAuthorizationManagerInitializer` | Cấu hình `AccessDecisionManager` theo API legacy |
| 3.0.0 | Reference của bản này vẫn hướng dẫn custom `AccessDecisionManager` | Không giả định hook mới đã có |
| **3.0.1** | Bổ sung `setAuthorizationManagerInitializer(Function<SecurityRule, AuthorizationManager<Object>>)` | Dùng custom `AuthorizationManager` |
| **3.0.2** | Có hook initializer | Dùng custom `AuthorizationManager` |
| **4.0.x** | Reference tiếp tục hỗ trợ custom `AuthorizationManager` | Dùng initializer và API Spring Security tương thích |

Javadoc của Web Flow ghi rõ `setAuthorizationManagerInitializer` có từ **3.0.1**. Các phương thức `getAccessDecisionManager`, `setAccessDecisionManager`, `getConfigAttributes` và `createAccessDecisionManager` bị đánh dấu deprecated for removal từ mốc này. Vì vậy:

- Dự án Web Flow 2.5.x: không gọi `setAuthorizationManagerInitializer`; phương thức này không có trong API của phiên bản.
- Dự án Web Flow 3.0.0: kiểm tra Javadoc đúng artifact trước khi viết theo ví dụ 3.0.1+.
- Dự án Web Flow 3.0.1/3.0.2 hoặc 4.0.x: dùng hook initializer được tài liệu hóa.

### 3.1. Phiên bản Spring Security cũng làm thay đổi chữ ký API

| Spring Security | API trừu tượng của `AuthorizationManager` | Ghi chú |
| --- | --- | --- |
| 5.5–6.3 | `check(Supplier<Authentication>, T)` trả `AuthorizationDecision` | API cũ của manager |
| **6.4–6.x** | `check(...)` vẫn còn nhưng deprecated; `authorize(...)` được bổ sung | Ưu tiên `authorize` khi viết code tường minh mới |
| **7.x** | `check(...)` bị loại; dùng `authorize(...)` trả `AuthorizationResult` | Không biên dịch implementation chỉ override `check` |

`AuthorizationDecision` triển khai `AuthorizationResult`, nên lambda trả `new AuthorizationDecision(true/false)` có thể dùng với functional interface của từng nhánh API. Tuy nhiên, nếu viết **anonymous class** và override method tường minh, phải override đúng chữ ký của phiên bản mục tiêu:

- Spring Security 5.5–6.3: override `check`.
- Spring Security 6.4–6.x: có thể override `authorize` để theo API mới, dù `check` vẫn còn.
- Spring Security 7.x: override `authorize`; `check` không còn.

### 3.2. Chọn đúng bộ phiên bản

| Tổ hợp minh họa | Đánh giá |
| --- | --- |
| Web Flow 2.5.x + Spring 5 + Security 5.x | Dùng listener legacy `AccessDecisionManager`; không có initializer |
| Web Flow 3.0.1/3.0.2 + Spring 6 + Security 6.x | Có initializer; Security 6.4+ khuyến nghị API `authorize` |
| Web Flow 4.0.x + Spring 7 + Security 7.x | Có initializer; phải dùng `authorize`, không dùng `check` |

Không chỉ nhìn số phiên bản Spring Framework. Hãy kiểm tra cả dependency thực tế của `spring-security-core`, `spring-security-config`, `spring-security-web`, `spring-webflow` và các starter/BOM.

## 4. Bảo vệ flow cần đủ ba thành phần

Tài liệu Web Flow mô tả quy trình ba bước:

1. Cấu hình Spring Security để xác thực và áp dụng chính sách HTTP.
2. Khai báo phần tử `secured` trong flow để xác định flow/state/transition cần bảo vệ.
3. Đăng ký `SecurityFlowExecutionListener` vào `FlowExecutor` để thực thi các rule đó.

Nếu chỉ thêm `<secured>` vào XML mà không đăng ký listener, **rule trong flow không được thực thi**. Nếu chỉ đăng ký listener mà không có rule, không có chính sách cụ thể nào được khai báo trong flow.

~~~mermaid
flowchart TD
    A["HTTP request tới flow"] --> B["Spring Security FilterChain"]
    B --> C["Authentication trong SecurityContext"]
    C --> D["Web Flow nhận flow execution"]
    D --> E["SecurityFlowExecutionListener"]
    E --> F["Đọc SecurityRule từ flow/state/transition"]
    F --> G["AuthorizationManagerInitializer chọn manager"]
    G --> H{"AuthorizationManager quyết định"}
    H -->|"Granted"| I["Cho phép vào state hoặc thực hiện transition"]
    H -->|"Denied"| J["Ném AccessDeniedException"]
    J --> K["Spring Security xử lý exception theo cấu hình"]
~~~

### 4.1. Phân biệt ba lớp bảo vệ

| Lớp | Bảo vệ gì? | Ví dụ |
| --- | --- | --- |
| HTTP request authorization | URL/HTTP request | `/admin/**` chỉ cho ADMIN |
| Flow authorization | Flow, state, transition | Chỉ người có `booking:read` được vào state review |
| Method/domain authorization | Service và dữ liệu nghiệp vụ | Chỉ chủ booking hoặc nhân viên được xác nhận booking |

Một người dùng có thể được phép truy cập URL `/booking` nhưng không có quyền vào state `review`. Ngược lại, việc flow listener cho phép transition không tự bảo vệ một REST endpoint khác gọi cùng service. Hãy đặt kiểm tra domain ở service/method khi quy tắc phụ thuộc tài nguyên.

## 5. Khai báo secured trong flow XML

Web Flow cho phép đặt phần tử `secured` ở ba cấp:

- **Flow:** bảo vệ việc bắt đầu flow.
- **State:** bảo vệ việc vào một state.
- **Transition:** bảo vệ việc thực hiện một transition.

Ví dụ flow đặt chỗ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow">

    <secured attributes="booking:read"/>

    <view-state id="details" view="booking/details">
        <transition on="next" to="review"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <secured attributes="booking:read"/>

        <transition on="back" to="details"/>
        <transition on="confirm" to="completed">
            <secured attributes="booking:confirm"/>
        </transition>
    </view-state>

    <end-state id="completed" view="booking/completed"/>
</flow>
~~~

Trong ví dụ:

- Muốn bắt đầu flow, người dùng cần rule `booking:read` ở cấp flow.
- State `review` cũng yêu cầu `booking:read`.
- Event `confirm` yêu cầu thêm `booking:confirm`.

Đây là permission dạng chuỗi minh họa, không phải role mặc định. Manager tùy chỉnh sẽ quyết định cách hiểu các chuỗi này. Nếu flow đã bị chặn ở cấp flow, rule ở state hoặc transition phía sau không thể mở lại quyền.

### 5.1. Thuộc tính attributes và match

`attributes` là danh sách chuỗi phân tách bằng dấu phẩy:

~~~xml
<secured attributes="booking:read, booking:export"/>
~~~

`match` có hai giá trị:

| Giá trị | Ý nghĩa |
| --- | --- |
| `any` | Chỉ cần một attribute được chấp nhận |
| `all` | Tất cả attribute đều phải được chấp nhận |

Mặc định là `any`. **Tài liệu Web Flow nêu `match` chỉ được áp dụng bởi manager mặc định**. Khi thay bằng custom `AuthorizationManager`, hãy đọc `SecurityRule#getComparisonType()` và tự thực hiện semantics `any`/`all` nếu chính sách của bạn cần giữ hành vi đó.

## 6. Đăng ký SecurityFlowExecutionListener

Một flow rule chỉ có hiệu lực khi listener được gắn vào executor.

### 6.1. Java configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.webflow.config.AbstractFlowConfiguration;
import org.springframework.webflow.definition.registry.FlowDefinitionRegistry;
import org.springframework.webflow.executor.FlowExecutor;
import org.springframework.webflow.security.SecurityFlowExecutionListener;

@Configuration
public class WebFlowSecurityConfiguration extends AbstractFlowConfiguration {
    @Bean
    FlowExecutor flowExecutor(
            FlowDefinitionRegistry flowRegistry,
            SecurityFlowExecutionListener securityFlowExecutionListener) {
        return getFlowExecutorBuilder(flowRegistry)
            .addFlowExecutionListener(securityFlowExecutionListener)
            .build();
    }
}
~~~

Đây là cấu hình skeleton. Khi thêm custom initializer ở mục 7, bean listener sẽ dùng policy service để chọn manager.

### 6.2. XML configuration

~~~xml
<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry">
    <webflow:flow-execution-listeners>
        <webflow:listener ref="securityFlowExecutionListener"/>
    </webflow:flow-execution-listeners>
</webflow:flow-executor>

<bean id="securityFlowExecutionListener"
      class="org.springframework.webflow.security.SecurityFlowExecutionListener"/>
~~~

Java Config và XML đều phải bảo đảm **đúng một listener được gắn vào executor đang chạy flow**. Nếu ứng dụng có nhiều `FlowExecutor`, kiểm tra listener đã được đăng ký cho executor xử lý flow cần bảo vệ.

## 7. Tùy chỉnh AuthorizationManager bằng initializer

Hook chính của Web Flow 3.0.1+ là:

~~~java
SecurityFlowExecutionListener#setAuthorizationManagerInitializer(
    Function<SecurityRule, AuthorizationManager<Object>> initializer
)
~~~

Initializer nhận một `SecurityRule` và trả về `AuthorizationManager<Object>` phù hợp với rule đó. Theo mặc định, `SecurityRule#getAuthorizationManager()` tạo manager dựa trên `AuthorityAuthorizationManager`. Bạn có thể thay mặc định bằng permission policy riêng.

### 7.1. Khai báo policy service

Ví dụ hệ thống dùng quyền `booking:read`, `booking:confirm` thay vì role:

~~~java
package com.example.security;

import org.springframework.security.core.Authentication;

public interface BookingPermissionPolicy {
    boolean hasPermission(Authentication authentication, String permission);
}
~~~

Implementation có thể kiểm tra authority trong `Authentication`, truy vấn permission store hoặc gọi policy service. Interface này tách logic nghiệp vụ khỏi listener và dễ mock trong unit test.

### 7.2. Tạo listener dùng custom manager

Đặt bean method dưới đây vào cùng class cấu hình có `flowExecutor` ở mục 6. Đây là method bổ sung cho class đó; không tạo thêm một class cùng tên.

~~~java
import java.util.Collection;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.core.Authentication;
import org.springframework.webflow.security.SecurityRule;

import com.example.security.BookingPermissionPolicy;

@Bean
SecurityFlowExecutionListener securityFlowExecutionListener(
            BookingPermissionPolicy permissionPolicy) {

        SecurityFlowExecutionListener listener =
            new SecurityFlowExecutionListener();

        listener.setAuthorizationManagerInitializer(rule -> {
            Collection<String> required = rule.getAttributes();

            return (authenticationSupplier, secureObject) -> {
                Authentication authentication = authenticationSupplier.get();

                if (authentication == null || !authentication.isAuthenticated()
                        || required == null || required.isEmpty()) {
                    return new AuthorizationDecision(false);
                }

                boolean granted;
                if (rule.getComparisonType() == SecurityRule.COMPARISON_ALL) {
                    granted = required.stream().allMatch(
                        permission -> permissionPolicy.hasPermission(
                            authentication, permission));
                } else if (rule.getComparisonType()
                        == SecurityRule.COMPARISON_ANY) {
                    granted = required.stream().anyMatch(
                        permission -> permissionPolicy.hasPermission(
                            authentication, permission));
                } else {
                    granted = false;
                }

                return new AuthorizationDecision(granted);
            };
        });

    return listener;
}
~~~

Đây là ví dụ Java theo kiểu lambda để tương thích với thay đổi method trừu tượng của `AuthorizationManager`: ở nhánh cũ, lambda triển khai `check`; ở Spring Security 7, lambda triển khai `authorize`. `AuthorizationDecision` cũng là một `AuthorizationResult`, nên cùng phần thân lambda có thể trả kết quả cho hai kiểu API. Khi viết anonymous class với `@Override`, bạn phải chọn đúng method của version mục tiêu.

### 7.3. Tại sao ví dụ đọc SecurityRule?

`SecurityRule` cung cấp:

- `getAttributes()`: các chuỗi permission được khai báo trong `secured`.
- `getComparisonType()`: chế độ `COMPARISON_ANY` hoặc `COMPARISON_ALL`.
- `getAuthorizationManager()`: manager mặc định dựa trên authority.

Manager được chọn dựa trên rule. Vì vậy, một flow có thể dùng nhiều loại permission và listener vẫn tái sử dụng một policy service.

### 7.4. Xử lý anonymous authentication

Trong Spring Security, anonymous token cũng có thể có `isAuthenticated() == true`. Nếu chính sách chỉ cho người dùng đã đăng nhập, không nên chỉ dựa vào `isAuthenticated()`. Hãy dùng `AuthenticationTrustResolver` hoặc kiểm tra anonymous token theo cách phù hợp với cấu hình:

~~~java
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;

AuthenticationTrustResolver trustResolver =
    new AuthenticationTrustResolverImpl();

if (authentication == null
        || !authentication.isAuthenticated()
        || trustResolver.isAnonymous(authentication)) {
    return new AuthorizationDecision(false);
}
~~~

Nếu có quyền cho anonymous user, hãy biểu diễn rõ bằng permission/rule riêng và test riêng. Không mặc định cho phép khi `Authentication` null hoặc không xác định.

## 8. Giữ manager mặc định cho role, dùng manager riêng cho permission

Không nhất thiết thay manager mặc định cho mọi rule. Nếu ứng dụng có cả role truyền thống và permission nghiệp vụ, initializer có thể chọn manager theo quy ước:

~~~java
listener.setAuthorizationManagerInitializer(rule -> {
    boolean roleRule = rule.getAttributes().stream()
        .allMatch(attribute -> attribute.startsWith("ROLE_"));

    if (roleRule) {
        return rule.getAuthorizationManager();
    }

    return customPermissionManager(rule, permissionPolicy);
});
~~~

Phương thức `customPermissionManager` là factory do ứng dụng tự viết, trả về `AuthorizationManager<Object>`. Cách này giữ hành vi mặc định cho các rule role-based và chỉ chuyển các rule permission sang policy riêng.

Nếu một rule trộn `ROLE_ADMIN` và `booking:confirm`, manager riêng phải định nghĩa rõ semantics `any`/`all` trên **toàn bộ danh sách**, hoặc từ chối cấu hình trộn. Không tự chia danh sách thành hai nhóm rồi cấp quyền theo cách không được mô tả.

## 9. Sử dụng AuthorizationManager theo API từng phiên bản

### 9.1. Spring Security 5.5–6.3: check

Trong các phiên bản này, method trừu tượng là:

~~~java
AuthorizationDecision check(
    Supplier<Authentication> authentication,
    Object object
);
~~~

Ví dụ class tường minh:

~~~java
public final class BookingAuthorizationManager
        implements AuthorizationManager<Object> {

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            Object secureObject) {
        Authentication current = authentication.get();
        boolean granted = current != null
            && permissionPolicy.hasPermission(current, "booking:read");
        return new AuthorizationDecision(granted);
    }
}
~~~

`verify` là method mặc định có thể gọi manager để kiểm tra và ném `AccessDeniedException` nếu bị từ chối. Với flow listener, hãy để listener thực hiện việc xử lý quyết định theo lifecycle của Web Flow.

### 9.2. Spring Security 6.4–6.x: ưu tiên authorize

Spring Security 6.4 bổ sung:

~~~java
AuthorizationResult authorize(
    Supplier<Authentication> authentication,
    Object object
);
~~~

Trong 6.4, `check` vẫn tồn tại và vẫn là method trừu tượng, nhưng đã deprecated; `authorize` được thêm dưới dạng method mặc định. Vì vậy, một class tường minh chỉ override `authorize` vẫn chưa đáp ứng interface 6.4 nếu không triển khai `check`. Với 6.4, có thể tiếp tục triển khai `check` để dùng method mặc định, hoặc triển khai cả hai nếu cần gọi API mới trực tiếp. Lambda ở mục 7 dùng method trừu tượng của đúng version và trả `AuthorizationDecision`, nên phù hợp cho ví dụ chạy theo từng dependency set.

### 9.3. Spring Security 7.x: không còn check

Spring Security 7 loại bỏ `AuthorizationManager#check` và dùng `authorize`. Một implementation chỉ override `check` sẽ không biên dịch với API 7.x. `AuthorizationDecision` triển khai `AuthorizationResult`, nên có thể trả nó từ `authorize`.

~~~java
public final class BookingAuthorizationManager
        implements AuthorizationManager<Object> {

    @Override
    public AuthorizationResult authorize(
            Supplier<? extends Authentication> authentication,
            Object secureObject) {
        Authentication current = authentication.get();
        boolean granted = current != null
            && permissionPolicy.hasPermission(current, "booking:read");
        return new AuthorizationDecision(granted);
    }
}
~~~

Chữ ký generic của `Supplier` trong source cần khớp đúng Javadoc của phiên bản đang biên dịch. Nếu implementation cần dùng chung nhiều nhánh, lambda thường đơn giản hơn anonymous class có `@Override`.

## 10. Bảo vệ flow, state và transition theo nguyên tắc tối thiểu quyền

Hãy khai báo rule gần với bước cần bảo vệ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <secured attributes="booking:read"/>

    <view-state id="search" view="booking/search">
        <transition on="select" to="review"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <secured attributes="booking:read"/>
        <transition on="back" to="search"/>
        <transition on="confirm" to="commitBooking">
            <secured attributes="booking:confirm"/>
        </transition>
    </view-state>

    <action-state id="commitBooking">
        <evaluate expression="bookingActions.confirm(draft)"/>
        <transition on="success" to="completed"/>
    </action-state>

    <end-state id="completed" view="booking/completed"/>
</flow>
~~~

Ở đây:

- Flow yêu cầu `booking:read`.
- Review cũng yêu cầu `booking:read`.
- Transition confirm yêu cầu `booking:confirm`.

Nếu state review không được bảo vệ, người dùng có thể thử truy cập trực tiếp state qua flow URL hợp lệ. Nếu chỉ ẩn nút Confirm trong HTML mà không bảo vệ transition, người dùng có thể gửi event trực tiếp. Phần tử `secured` đặt trên transition giúp kiểm tra ngay trước khi transition chạy.

### 10.1. Flow-level rule và state-level rule có thể lặp lại

Lặp rule ở flow và state không phải lúc nào cũng cần. Flow-level rule thích hợp khi mọi bước đều yêu cầu quyền cơ bản. State-level rule phù hợp khi có bước chứa dữ liệu nhạy cảm hơn. Chọn cấu trúc giúp người đọc hiểu chính sách mà không tạo quá nhiều rule trùng lặp.

### 10.2. Không dùng flow security để ẩn giao diện

Authorization quyết định request có được thực thi hay không. Việc ẩn nút hoặc menu theo role chỉ là cải thiện trải nghiệm. Server phải kiểm tra lại ở listener/service vì client có thể gửi event hoặc URL trực tiếp.

## 11. Ranh giới với Spring Security HTTP và method security

Một cấu hình HTTP cơ bản có thể yêu cầu người dùng đăng nhập trước khi vào các URL flow:

~~~java
@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/login", "/assets/**").permitAll()
        .anyRequest().authenticated()
    );
    return http.build();
}
~~~

Đoạn trên chỉ minh họa bảo vệ request. Nó không thay `SecurityFlowExecutionListener` và cũng không quyết định permission cụ thể cho từng state/transition.

Với service nghiệp vụ, có thể bật method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}

@Service
class BookingService {
    @PreAuthorize("hasAuthority('booking:confirm')")
    public Confirmation confirm(BookingCommand command) {
        // Kiểm tra chủ sở hữu, trạng thái, dữ liệu và commit.
        return doConfirm(command);
    }
}
~~~

Nếu quyền phụ thuộc booking cụ thể, hãy kiểm tra owner/tenant ở service hoặc một domain policy riêng. Ví dụ `hasAuthority('booking:confirm')` chỉ xác nhận quyền tổng quát, không tự chứng minh người gọi được sửa mọi booking.

## 12. Quy tắc fail-closed và xử lý exception

Một custom manager cần có hành vi rõ khi không đủ dữ liệu:

| Tình huống | Quyết định khuyến nghị |
| --- | --- |
| `Authentication` null | Deny |
| Anonymous user nhưng rule yêu cầu đăng nhập | Deny |
| `SecurityRule` không có attribute | Deny hoặc fail cấu hình sớm |
| Permission không tồn tại | Deny |
| Policy service không phản hồi | Không tự động allow |
| Manager không thể quyết định | Không trả kết quả mơ hồ nếu listener không hỗ trợ abstain theo policy |
| Có exception khi truy vấn policy | Propagate hoặc chuyển thành deny theo chính sách được định nghĩa; không allow |

`AccessDeniedException` do listener ném phải được phép đi lên stack để Spring Security xử lý, ví dụ chuyển tới login hoặc access-denied handler. Không bắt exception rồi chỉ log và tiếp tục transition.

Không nên:

- Catch mọi `RuntimeException` rồi trả `new AuthorizationDecision(true)`.
- Dùng `null` để biểu thị “chưa biết” nhưng không có quy tắc xử lý abstain.
- Đọc principal từ request parameter hoặc hidden field.
- Cache quyền vô thời hạn khiến quyền đã thu hồi vẫn được dùng.
- Gọi service từ initializer để giữ kết quả theo singleton nếu kết quả phụ thuộc người dùng/request.

## 13. Kiểm thử AuthorizationManager và flow security

Kiểm thử cần chứng minh cả hai chiều **được phép** và **bị từ chối**, không chỉ xác nhận một manager trả true.

### 13.1. Unit test cho policy manager

Với policy manager ở mục 7, hãy kiểm tra:

~~~java
@Test
void deniesWhenAuthenticationIsMissing() {
    AuthorizationManager<Object> manager =
        createManagerFor(Set.of("booking:read"), SecurityRule.COMPARISON_ANY);

    AuthorizationDecision decision = (AuthorizationDecision) manager.check(
        () -> null, new Object());

    assertFalse(decision.isGranted());
}
~~~

Đoạn test minh họa API `check` ở Spring Security 6.x trước 7.0. Khi test trên Spring Security 7, gọi `authorize` và nhận `AuthorizationResult`; không giữ lời gọi `check`.

Các test cần có:

- User có đúng permission → granted.
- User thiếu permission → denied.
- User anonymous → denied nếu rule yêu cầu đăng nhập.
- Hai permission với `COMPARISON_ANY` → một permission đủ.
- Hai permission với `COMPARISON_ALL` → phải có cả hai.
- Danh sách permission rỗng hoặc comparison type không hợp lệ → fail-closed.
- Policy service lỗi → không cấp quyền ngoài ý muốn.

### 13.2. Integration test cho SecurityFlowExecutionListener

Đăng ký listener vào `FlowExecutor`, tạo flow XML có `<secured>` ở flow/state/transition, rồi kiểm tra:

| ID | Bối cảnh | Kết quả kỳ vọng |
| --- | --- | --- |
| S01 | User có `booking:read`, mở flow | Bắt đầu flow thành công |
| S02 | User thiếu `booking:read`, mở flow | Bị từ chối trước khi vào flow |
| S03 | Có `booking:read`, vào state review | State được phép hiển thị |
| S04 | Thiếu `booking:confirm`, gửi event confirm | Transition bị từ chối |
| S05 | Có cả read và confirm | Transition confirm được phép |
| S06 | Rule `match="all"` và chỉ có một permission | Bị từ chối |
| S07 | Rule `match="any"` và có một permission | Được phép nếu manager thực hiện any |
| S08 | Authentication anonymous | Bị từ chối theo policy |
| S09 | Policy service ném exception | Không có đường allow mặc định |
| S10 | AccessDeniedException thoát listener | Spring Security xử lý đúng |
| S11 | Request URL được bảo vệ nhưng không có flow rule | HTTP layer vẫn chặn/cho phép theo cấu hình riêng |
| S12 | Service được gọi từ controller khác | Method/domain authorization vẫn được áp dụng |

### 13.3. Kiểm tra cả ba lớp bảo vệ

Một test chỉ gọi `AuthorizationManager` không chứng minh HTTP filter và service đã được cấu hình. Dùng `MockMvc` hoặc HTTP integration test để kiểm tra request; dùng flow test để kiểm tra listener; dùng method/security test cho service. Nếu policy dựa vào database, nên có test tích hợp với repository hoặc policy adapter thật.

## 14. Chuyển từ AccessDecisionManager sang AuthorizationManager

Với Web Flow 2.5.x, cấu hình legacy thường có dạng:

~~~xml
<bean id="securityFlowExecutionListener"
      class="org.springframework.webflow.security.SecurityFlowExecutionListener">
    <property name="accessDecisionManager" ref="myAccessDecisionManager"/>
</bean>
~~~

Ở Web Flow 3.0.1+, API `setAccessDecisionManager` bị deprecated for removal và thay bằng `setAuthorizationManagerInitializer`. Hãy chuyển dần theo các bước:

1. Liệt kê các `ConfigAttribute`/role hiện dùng trong flow.
2. Chuyển mỗi rule thành permission hoặc authority có ngữ nghĩa rõ.
3. Viết policy service và custom manager; không chuyển nguyên voting logic một cách máy móc.
4. Định nghĩa rõ semantics `any`/`all`, abstain và lỗi policy.
5. Đăng ký listener và xác minh flow executor đang dùng listener đó.
6. Kiểm thử allow/deny ở flow, state, transition và service.
7. Sau khi xác minh, bỏ cấu hình legacy và dependency tương thích cũ nếu không còn cần.

Spring Security 7 chuyển các API legacy như `AccessDecisionManager`/`AccessDecisionVoter` sang module tùy chọn `spring-security-access`. Với dự án mới trên Spring Security 7, ưu tiên `AuthorizationManager`; chỉ giữ module legacy khi còn code cũ thực sự cần nó.

### 14.1. Nếu đang ở Web Flow 2.5.x?

Không thể gọi setter chưa tồn tại. Có hai hướng:

- Giữ custom `AccessDecisionManager` theo API Web Flow 2.5.x và lập kế hoạch nâng cấp.
- Nếu cần policy mới trước khi nâng cấp, xây một integration listener riêng có kiểm soát hoặc bảo vệ service/method ở lớp Spring Security hiện tại; không giả vờ rằng `SecurityFlowExecutionListener` 2.5 đã hỗ trợ initializer.

Không nên copy code Web Flow 3.0.1 vào dự án 2.5 rồi chữa compile bằng reflection. Reflection không tạo ra contract tích hợp được framework hỗ trợ.

## 15. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `setAuthorizationManagerInitializer` không tìm thấy | Web Flow 2.5.x hoặc 3.0.0 | Kiểm tra version; hook có từ 3.0.1 |
| `AuthorizationManager` không tìm thấy | Spring Security quá cũ hoặc thiếu core dependency | Kiểm tra dependency tree |
| `check` không còn trong API | Spring Security 7 | Override `authorize` |
| `authorize` không phải abstract method | Spring Security trước 6.4 | Dùng `check` hoặc lambda theo version |
| `<secured>` không có tác dụng | Chưa đăng ký listener vào FlowExecutor | Kiểm tra flow execution listeners |
| User có permission nhưng bị deny | Custom manager hiểu sai attribute hoặc any/all | Log rule attributes và comparison type an toàn |
| User thiếu permission vẫn vào được | Manager trả true khi null/exception/empty rule | Fail-closed và test deny |
| `match="all"` không hoạt động | Custom manager thay manager mặc định nhưng không xử lý comparison | Đọc `SecurityRule.getComparisonType()` |
| Spring Security không redirect sau deny | Exception bị catch/swallow trong listener/action | Để `AccessDeniedException` đi lên stack |
| Flow được phép nhưng REST endpoint cũng mở | Chỉ bảo vệ flow state | Thêm HTTP/method/domain authorization |
| Một user sửa được booking của user khác | Chỉ kiểm tra authority tổng quát | Kiểm tra owner/tenant tại service |
| Security 7 báo thiếu `AccessDecisionManager` | Còn dùng API legacy đã chuyển module | Chuyển sang AuthorizationManager hoặc thêm module legacy có chủ đích |

## 16. Bài tập thực hành

### Bài A — quyền permission thay cho role

Khai báo `booking:read` và `booking:confirm` trong flow. Viết `BookingPermissionPolicy` kiểm tra các authority tương ứng. Đăng ký initializer và listener. Kiểm tra người có read nhưng thiếu confirm chỉ xem được review, không xác nhận được.

### Bài B — hỗ trợ any và all

Tạo hai rule: một rule `match="any"` cho `booking:read, booking:preview`; một rule `match="all"` cho `booking:read, booking:confirm`. Viết test xác nhận custom manager thực hiện đúng `SecurityRule.COMPARISON_ANY` và `SecurityRule.COMPARISON_ALL`.

### Bài C — dùng manager mặc định cho role, manager riêng cho permission

Trong initializer, nếu toàn bộ attribute bắt đầu bằng `ROLE_`, trả `rule.getAuthorizationManager()`. Nếu rule chứa permission nghiệp vụ, trả custom manager. Thử rule trộn role và permission rồi quyết định rõ có cho phép hay từ chối cấu hình đó.

### Bài D — nâng từ Spring Security 6.3 lên 6.4

Tạo một manager class tường minh đang override `check`. Chuyển sang `authorize`, đổi kiểu trả về `AuthorizationResult`, sau đó chạy test ở cả hai dependency set hoặc tạo hai source set nếu dự án cần hỗ trợ song song.

### Bài E — nâng lên Spring Security 7

Xóa mọi implementation chỉ override `check`. Xác minh `AuthorizationDecision` được trả từ `authorize`, kiểm tra module `spring-security-access` không bị kéo vào ngoài ý muốn và test lại listener Web Flow 4.x.

### Bài F — kiểm tra quyền theo chủ sở hữu

Bảo vệ state review bằng permission chung `booking:read`, sau đó thêm method security/service check xác minh người dùng có quyền đọc booking ID đang mở. Thử đổi ID trên request và xác nhận service từ chối.

## 17. Checklist triển khai

- [ ] Đã xác nhận Web Flow có hỗ trợ `setAuthorizationManagerInitializer` (3.0.1+).
- [ ] Spring Framework và Spring Security đúng thế hệ tương thích với Web Flow.
- [ ] Không gọi `check` trong implementation đích Spring Security 7.
- [ ] `SecurityFlowExecutionListener` được đăng ký vào đúng `FlowExecutor`.
- [ ] Flow/state/transition nhạy cảm có `<secured>` tương ứng.
- [ ] Custom initializer nhận và xử lý `SecurityRule`.
- [ ] Manager xử lý `Authentication` null/anonymous theo chính sách.
- [ ] Rule rỗng hoặc permission không xác định bị từ chối.
- [ ] Semantics `any`/`all` được xử lý rõ trong custom manager.
- [ ] Không trả allow khi policy service lỗi hoặc không thể quyết định.
- [ ] `AccessDeniedException` được truyền lên Spring Security.
- [ ] HTTP request authorization vẫn được cấu hình riêng.
- [ ] Service/method kiểm tra quyền trên tài nguyên cụ thể.
- [ ] Có test allow, deny, anonymous, any/all, flow/state/transition.
- [ ] Có test trên đúng version Spring Security mục tiêu.
- [ ] API legacy chỉ được giữ khi có lý do và dependency rõ ràng.

## 18. Câu hỏi tự kiểm tra

**1. AuthorizationManager khác AuthenticationManager thế nào?** AuthenticationManager xác thực danh tính; AuthorizationManager quyết định quyền truy cập.

**2. Spring Web Flow có hỗ trợ initializer từ phiên bản nào?** `SecurityFlowExecutionListener#setAuthorizationManagerInitializer` có từ Web Flow 3.0.1.

**3. Web Flow 2.5.x có thể gọi setter này không?** Không; API listener của dòng đó dùng AccessDecisionManager.

**4. Vì sao chỉ khai báo `<secured>` là chưa đủ?** FlowExecutor phải gắn SecurityFlowExecutionListener để thực thi rule.

**5. SecurityRule cung cấp thông tin gì?** Danh sách attributes và comparison type, cùng manager mặc định.

**6. Custom manager có tự hiểu `match="all"` không?** Không nên giả định; khi thay manager mặc định, hãy đọc comparison type và thực hiện semantics rõ ràng.

**7. Vì sao `Authentication.isAuthenticated()` chưa đủ để loại anonymous?** AnonymousAuthenticationToken có thể được đánh dấu authenticated; dùng trust resolver hoặc policy phù hợp.

**8. `check` thay đổi thế nào trong Spring Security?** `check` là API cũ; `authorize` có từ 6.4, `check` deprecated ở 6.4 và bị loại ở 7.0.

**9. Listener flow có thay thế method security không?** Không. Service có thể được gọi từ controller, batch hoặc API khác; kiểm tra domain cần nằm ở service.

**10. Khi bị từ chối, có nên nuốt AccessDeniedException không?** Không. Để Spring Security xử lý exception theo authentication entry point/access-denied handler.

## 19. Tài liệu tham khảo

1. [Spring Web Flow 3.0.2 Reference — Securing Flows](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — phần 16, secured element, SecurityFlowExecutionListener và custom AuthorizationManager.
2. [SecurityFlowExecutionListener Javadoc 3.0.1](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/webflow/security/SecurityFlowExecutionListener.html) — `setAuthorizationManagerInitializer`, API legacy và mốc `Since 3.0.1`.
3. [SecurityRule Javadoc](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/security/SecurityRule.html) — attributes, comparison type và manager mặc định.
4. [Spring Web Flow 2.5.1 Reference](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/) — tích hợp listener và custom AccessDecisionManager của dòng cũ.
5. [Spring Security 6.4 AuthorizationManager Javadoc](https://docs.spring.io/spring-security/site/docs/6.4.10/api/org/springframework/security/authorization/AuthorizationManager.html) — `check` deprecated và `authorize` được bổ sung từ 6.4.
6. [Spring Security 7.0 What’s New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html) — loại bỏ `AuthorizationManager#check` và chuyển sang `authorize`.
7. [Spring Security Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html) — Authentication, GrantedAuthority, AuthorizationManager và custom policy.
8. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html) — custom manager và bảo vệ method.
9. [Spring Blog — Access API Moves to Spring Security Access](https://spring.io/blog/2025/09/09/access-api-moves-to-spring-security-access/) — vị trí module legacy Access API ở Spring Security 7.

**Điểm cần nhớ:** Với Web Flow 3.0.1 trở lên, `SecurityFlowExecutionListener#setAuthorizationManagerInitializer` cho phép chọn một `AuthorizationManager` theo từng `SecurityRule`. Hãy kiểm tra cả phiên bản Web Flow lẫn chữ ký Spring Security: `check` thuộc API cũ, `authorize` là hướng mới và là API bắt buộc ở Spring Security 7. Flow listener bảo vệ flow/state/transition; request filter và service vẫn cần kiểm tra quyền ở các ranh giới tương ứng.
