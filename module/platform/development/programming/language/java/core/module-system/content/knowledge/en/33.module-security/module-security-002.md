# Do Not Treat Module Boundaries as Business Authorization

## 1. Objective

The Java Platform Module System (JPMS) creates boundaries between modules to control dependencies, package accessibility, and the level of implementation encapsulation. These boundaries help organize code cleanly and prevent other modules from arbitrarily depending on internal packages.

However, **module boundaries are not a business authorization mechanism for users**. JPMS does not know who is logged in, which tenant they belong to, what role they hold, or which resources they are allowed to read or modify.

Two questions must be distinguished:

- **Module access:** Which module's code can read another module, access public types in which package, or perform deep reflection where?
- **Business authorization:** Is an authenticated user or service allowed to perform a specific action on a specific resource?

These two layers of control complement each other. Module encapsulation helps protect code structure and limit unintended technical access. Business authorization must be implemented at the application/service layer based on actual identity, permissions, and resources.

## 2. What Does JPMS Control?

A named module can declare dependencies and package boundaries in `module-info.java`:

~~~java
module com.acme.orders {
    requires com.acme.persistence;

    exports com.acme.orders.api;
}
~~~

Directives that apply at the module level:

- **requires**: declares that the current module needs to read another module.
- **exports**: exposes a package for other modules to access APIs per Java language rules.
- **exports ... to**: exports a package only to a list of named modules.
- **opens**: opens a package for deep reflection at runtime.
- **opens ... to**: opens a package only to a specific list of modules.
- **uses / provides**: declares that a module uses or provides a service.

For example, an implementation module can keep internal packages unexported:

~~~text
com.acme.orders
  com.acme.orders.api
  com.acme.orders.internal
~~~

The module descriptor only exports the API package:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Other modules can use public APIs in `com.acme.orders.api` if other readability and access conditions are met. Code in other modules cannot arbitrarily import public classes in the `com.acme.orders.internal` package through normal access mechanisms.

This is a useful technical boundary: the implementation can be changed without turning internal packages into a contract for the entire system.

## 3. Why Are Module Boundaries Not Business Authorization?

JPMS does not model end-user identity. A module does not know:

- Which account the user logged in with.
- Whether the user has the `ADMIN`, `MANAGER`, or `VIEWER` role.
- Which organization or tenant the user belongs to.
- Whether they have permission to read this invoice but not another invoice.
- Whether they are allowed to refund, approve, or delete data at the current time.

Suppose module `com.acme.orders` exports an API:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

A controller, batch job, or another module can call that API. When a request comes from user Alice or Bob, the JVM still executes the calling module's code under the same module identity. JPMS does not automatically change access rights based on the account sending the HTTP request.

If the API does not check business permissions, any caller that can access the API and construct a valid request can attempt to perform the operation the API provides.

For example, the fact that module `com.acme.admin` is allowed to read an internal package does not prove that the person using the admin screen has administrative privileges. A module name is the identity of code in the module graph, not the authenticated identity of a user.

### Qualified Exports Are Still Not Role-Based Access Control

You can write:

~~~java
module com.acme.orders {
    exports com.acme.orders.admin to com.acme.admin;
}
~~~

This declaration restricts which module can access the `com.acme.orders.admin` package according to module access rules. It does not check whether the user has the `ADMIN` role.

All code running in module `com.acme.admin` shares the same module identity when evaluating this relationship. The module system does not distinguish that Alice is an admin while Bob is only a staff member when both requests pass through the same module.

Qualified exports are useful for limiting dependencies between code components. Do not use them as a substitute for checking principal permissions or per-resource permissions.

## 4. Authentication, Authorization, and Module Encapsulation Are Three Distinct Concepts

| Concept | Question to Answer | Example Mechanisms |
|---|---|---|
| Authentication | Who is calling? | Verifying session, token, certificate, service identity |
| Authorization | What is this caller allowed to do on which resource? | Role, permission, policy, tenant/resource ownership |
| Module encapsulation | Which module's code can access which package/API? | `requires`, `exports`, `opens`, `module-info.java` |

Authentication produces a verified identity. Authorization uses that identity along with policies and resource information to decide whether to allow or deny an operation.

JPMS does not replace these two steps. Conversely, a good authorization system does not make the module descriptor redundant: module encapsulation still helps reduce coupling, protect implementations, and prevent code from depending on unexposed APIs.

For example, a request might go through:

1. The server verifies the access token and obtains a trusted principal.
2. The application determines the action the request wants to perform.
3. The service loads the resource to operate on.
4. The authorization policy checks whether the principal has permission to perform the action on that resource.
5. Only when the policy allows it does the service perform the modification.
6. The system records an appropriate audit event.

Module boundaries support code structure in these steps; they do not decide step 4 by themselves.

## 5. Performing Authorization at the Service Layer

Suppose a system manages invoices. Users may only read invoices belonging to their tenant and must have the appropriate permission.

One way to organize the module:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

The `com.acme.billing.internal` package contains the repository and internal implementation. The API package provides services to valid callers of the application.

Illustrative example:

~~~java
public final class InvoiceService {
    private final InvoiceRepository repository;
    private final AuthorizationService authorization;

    public InvoiceService(
            InvoiceRepository repository,
            AuthorizationService authorization) {
        this.repository = repository;
        this.authorization = authorization;
    }

    public Invoice findInvoice(
            AuthenticatedPrincipal actor,
            InvoiceId invoiceId) {

        Invoice invoice = repository.findById(invoiceId)
                .orElseThrow(InvoiceNotFoundException::new);

        authorization.requireAllowed(
                actor,
                Permission.INVOICE_READ,
                invoice.tenantId());

        return invoice;
    }
}
~~~

Here:

- **AuthenticatedPrincipal** represents the identity verified by the server.
- **Permission.INVOICE_READ** is the business action.
- **invoice.tenantId()** identifies the resource scope.
- **requireAllowed** rejects the request if the principal lacks permission.

Do not obtain the principal by trusting an arbitrary `userId` or role sent by the client. The principal must come from a trusted authentication context, such as a verified token or server-side session.

Similarly, update, delete, approve, and refund operations all require appropriate policies. The fact that a user sees an Edit button in the UI does not prove they are allowed to call the update API.

## 6. Check Permissions per Resource, Not Just per Feature

A common mistake is checking only whether the user has permission to access the feature:

~~~java
if (actor.hasPermission(Permission.INVOICE_READ)) {
    return repository.findById(invoiceId);
}
~~~

This code is not necessarily safe. If `invoiceId` belongs to another tenant, the user could read data outside their permitted scope.

Authorization needs to consider at least:

- **Subject:** who is performing the action?
- **Action:** what do they want to do?
- **Resource:** which object is being affected?
- **Context:** tenant, workflow state, time, risk level, or relevant business conditions.

For example:

~~~java
authorization.requireAllowed(
        actor,
        Permission.INVOICE_APPROVE,
        invoice.id(),
        invoice.tenantId(),
        invoice.status());
~~~

The policy might require the approver to belong to the same tenant, hold the `APPROVE` permission, and for the invoice to be in the `PENDING` state.

Server-side authorization must be checked for every request that can access data or change state. Do not rely on hard-to-guess IDs, hidden URLs, UI menus, or unexported modules to prevent unauthorized access.

## 7. How Do Module Boundaries Support Security?

Module encapsulation still has security value within an appropriate scope.

### Reduce Public API

Export only packages needed by callers. Keep implementations, helpers, internal repositories, and sensitive classes in unexported packages whenever possible.

~~~java
module com.acme.identity {
    exports com.acme.identity.api;
}
~~~

Other modules depend on the stable API instead of directly accessing internal packages. This reduces the technical access surface and limits external code from accidentally calling implementation details.

### Limit Deep Reflection

Do not open packages with `opens` unless there is a specific need. Frameworks needing reflection can be granted access to open the right package to the right module:

~~~java
module com.acme.identity {
    opens com.acme.identity.model to com.acme.json;
}
~~~

Avoid using `open module` if only a few packages need deep reflection. Opening too broadly can allow frameworks or code in the designated module to deeply access more implementation details than necessary.

### Reduce Unnecessary Dependencies

Use `requires` to declare truly needed dependencies. Do not bring sensitive modules into the graph merely for the convenience of calling a helper class. Separating API and implementation into appropriate modules can make dependencies clearer.

### Protect Architectural Integrity

Modules that do not export internal packages help the compiler and runtime detect access that violates the design. When APIs change, code that depends on internal implementations has less chance of silently continuing to work.

These benefits support defense in depth and maintainability. They do not replace authorization for each user, action, and resource.

## 8. Limitations to Remember

### Module Identity Is Not User Identity

A module name identifies a module in the module graph. It does not represent a user account, role, tenant, or database permission.

### Public APIs Still Need Permission Checks

A public method in an exported package can be called by many components. If the method performs a sensitive operation, the application/service layer itself must enforce the authorization policy.

### `opens` Does Not Grant Business Permissions

`opens` allows deep reflection according to module access rules. It does not grant permission to read invoice data, transfer money, or modify accounts under business policies.

### `requires` Does Not Mean Permission to Perform All Actions

`requires` creates a readability relationship. It does not grant the `ADMIN` role, does not grant permissions on data, and does not prove the caller is authenticated.

### Classpath and Unnamed Module Need Attention

Code running on the classpath belongs to the unnamed module. The unnamed module reads every module. That does not make it a trusted security principal, nor does it create a business policy. Understand clearly which modules are actually exported to the unnamed module when configuring the application.

### Reflection and Runtime Options Can Change Encapsulation Levels

Options such as **--add-exports** and **--add-opens** can expand module access in the runtime configuration. For packages opened to **ALL-UNNAMED**, code on the classpath can receive corresponding access rights.

Some runtime APIs also allow adjusting module relationships under certain caller conditions. Therefore, command lines, startup scripts, build configurations, and JVM operational permissions must be controlled.

Do not treat the fact that a package is not exported in `module-info.java` as the sole proof that business data is protected.

### JPMS Is Not a Sandbox for Untrusted Code

Modules running together in a single JVM do not automatically have separate process isolation. Code loaded and executed in the process can use the process's APIs, threads, resources, and permissions within existing runtime limits.

If you must run untrusted plugins or extensions, do not rely on module boundaries to isolate them. Consider separate processes/containers, separate OS identities, filesystem/network restrictions, separate credentials, and controlled communication protocols. Isolation design must match the actual threat model.

## 9. Defense in Depth for Modular Applications

A secure system typically combines multiple layers:

1. **Authentication:** verify user or service identity; validate signature, issuer, audience, expiry, and required claims.
2. **Authorization:** check action and resource on the server side; apply least privilege and deny by default.
3. **Tenant isolation:** ensure queries and operations are always scoped to the correct tenant; do not check only in the UI or controller.
4. **Data layer:** use a database account with minimal privileges; consider row-level security or appropriate constraints to protect data at the storage layer.
5. **Module encapsulation:** export only necessary APIs; limit `opens` and unnecessary dependencies.
6. **Runtime isolation:** separate processes/containers when running code with different trust levels; restrict network, filesystem, and secrets.
7. **Audit and monitoring:** record who performed what action on which resource, allow/deny outcomes, and appropriate correlation IDs.

Not every system needs every technique at the same level of complexity. Choose measures based on data sensitivity, action impact, and threat model. However, every sensitive operation must have an explainable and testable authorization decision.

## 10. Example Distinguishing Module Access from Business Authorization

Suppose we have two modules:

~~~java
module com.acme.admin {
    requires com.acme.billing;
}
~~~

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

Both the `admin` module and the `web` module can depend on the `billing` API if the module graph and package access allow it.

This only answers whether code can call the API. It does not decide whether the user sending the request is allowed to perform an administrative operation.

For example:

~~~java
public void refundInvoice(
        AuthenticatedPrincipal actor,
        InvoiceId invoiceId) {

    Invoice invoice = repository.findById(invoiceId)
            .orElseThrow(InvoiceNotFoundException::new);

    authorization.requireAllowed(
            actor,
            Permission.INVOICE_REFUND,
            invoice.tenantId());

    paymentGateway.refund(invoice.paymentReference());
}
~~~

If `actor` lacks the `refund` permission in the corresponding tenant, the service must deny it regardless of whether the caller is in the `admin`, `web`, or `batch` module.

A separate module containing authorization policies can be added, exporting only the necessary APIs. However, every call path to a sensitive operation must still go through policy enforcement. If another public method bypasses the check, a good module structure will not prevent that bug.

## 11. Design and Review Checklist

When designing modules:

- Export only packages that are genuinely the module's API.
- Keep internal implementations in unexported packages when possible.
- Use `opens` only for packages and framework modules that genuinely need reflection.
- Check `--add-exports`, `--add-opens`, and `ALL-UNNAMED` options in runtime configurations.
- Do not treat a module name as a user identity or role.
- Do not treat `requires` as permission to operate on data.
- Do not run untrusted code in the same JVM relying solely on module encapsulation.

When designing authorization:

- Is the principal created from a verified authentication context?
- Does every sensitive action check permissions on the server side?
- Does the policy consider the resource, tenant, and business state?
- Do read, update, delete, approve, and refund operations each have appropriate checks?
- Is cross-tenant access prevented when the client alters an ID in the request?
- Is access denied by default when a policy or context is missing?
- Are authorization decisions audited and are deny cases tested?
- Do the database and infrastructure have appropriate least-privilege permissions?

## 12. Self-Check Exercises and Answers

### Exercise 1 — Does the admin module mean an admin user?

A request passes through module `com.acme.admin`. Can we conclude the sender has the `ADMIN` role?

**Answer:** No. Module identity identifies code/module in the runtime graph, not the identity of the logged-in user. The principal must be obtained from the authentication context and checked for roles/permissions.

### Exercise 2 — Does an unexported package protect invoices from unauthorized access?

A package containing `InvoiceRepository` is not exported. Is that enough to ensure users cannot read invoices from another tenant?

**Answer:** No. Encapsulation restricts other modules' code from accessing internal packages per module rules. Authorization must check the principal, action, invoice, and tenant on the server side; the data layer can add isolation.

### Exercise 3 — Are qualified exports RBAC?

The billing module declares:

~~~java
exports com.acme.billing.admin to com.acme.admin;
~~~

Can this declaration be used to ensure only users with the `ADMIN` role can refund invoices?

**Answer:** No. Qualified exports restrict the caller module, not individual users executing through that module. Refunds must still check permissions on the resource.

### Exercise 4 — Does `opens` grant permission to read business data?

The `model` module opens a package to the `JSON` module using `opens`. Is the `JSON` module automatically allowed to read all customer records?

**Answer:** No. `opens` only relates to deep reflection on a package at runtime. Permission to read customer records must be determined by application authorization and data access policies.

### Exercise 5 — Should untrusted plugins run in a separate module?

A plugin is placed in its own named module and does not export any packages. Can the plugin be considered sandboxed?

**Answer:** No. Modules running in the same JVM do not have automatic process isolation. For untrusted code, evaluate process/container isolation and OS, filesystem, network, and credential restrictions.

### Exercise 6 — Are UI permissions enough?

The UI only shows the Delete button to users with permission. Does the API need to check again when receiving a `DELETE` request?

**Answer:** Yes. Clients can craft requests without using the UI. The server must authenticate the principal and check permissions on the resource before performing the operation.

### Exercise 7 — Does `requires` grant ADMIN privileges?

Module `com.acme.admin` declares `requires com.acme.billing`. Does that grant admin privileges over billing data?

**Answer:** No. `requires` creates a readability relationship between modules. Roles and permissions on data are separate business policies.

### Exercise 8 — Where should tenant checks happen?

A user has the `INVOICE_READ` permission, but `invoiceId` belongs to another tenant. Is checking only the general permission enough?

**Answer:** No. Resource and tenant scope must be checked. Authorization must evaluate subject, action, resource, and context together.

**Takeaway:** JPMS controls which code can access which APIs and packages. Business authorization decides whether an authenticated principal is permitted to perform an action on a specific resource. Use module encapsulation to keep architecture clean; use server-side policy enforcement to protect data and business logic.

## References

- Oracle Java SE 21 — Java Platform Module System, module declarations and access control: https://docs.oracle.com/en/java/javase/21/docs/specs/jls/jls-7.html
- Oracle Java SE 21 API — Module: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Oracle Java SE 21 — javac options `--add-exports` and `--add-reads`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Oracle Java SE 21 — java launcher options `--add-exports` and `--add-opens`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- OpenJDK JEP 261 — Module System: https://openjdk.org/jeps/261